# -*- coding: utf-8 -*-
# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: light
#       format_version: '1.5'
#       jupytext_version: 1.10.1
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# +
# %load_ext autoreload
# %autoreload 2

# %matplotlib inline

import os
os.environ['TORCH_HOME'] = "/media/hdd/Datasets/"
import sys
sys.path.append("../")
# -

from sprintdl.main import *
from sprintdl.nets import *

device = torch.device('cuda',0)
from torch.nn import init
import torch
import math

# # Define required

# +
fpath = Path("/media/hdd/Datasets/ArtClass/")

tfms = [make_rgb, ResizeFixed(128), to_byte_tensor, to_float_tensor]
bs = 256
# -

# # Actual process

il = ImageList.from_files(fpath, tfms=tfms)

il

tm= Path("/media/hdd/Datasets/ArtClass/Unpopular/mimang.art/69030963_140928767119437_3621699865915593113_n.jpg")

sd = SplitData.split_by_func(il, partial(random_splitter, p_valid = .2))
ll = label_by_func(sd, lambda x: str(x).split("/")[-3], proc_y=CategoryProcessor())

n_classes = len(set(ll.train.y.items))

data = ll.to_databunch(bs, c_in=3, c_out=2)

show_batch(data, 4)


def lin_comb(v1, v2, beta): 
    print(beta.shape, v1.shape, v2.shape)
    return beta.T*v1 + (1-beta)*v2


class MixUp(Callback):
    _order = 90 
    def __init__(self, α:float=0.4): self.distrib = Beta(tensor([α]), tensor([α]))
    
    def begin_fit(self): self.old_loss_func,self.run.loss_func = self.run.loss_func,self.loss_func
    
    def begin_batch(self):
        if not self.in_train: return 
        λ = self.distrib.sample((self.yb.size(0),)).squeeze().to(self.xb.device)
        λ = torch.stack([λ, 1-λ], 1)
        self.λ = unsqueeze(λ.max(1)[0], (1,2,3))
        shuffle = torch.randperm(self.yb.size(0)).to(self.xb.device)
        xb1,self.yb1 = self.xb[shuffle],self.yb[shuffle]
        self.run.xb = lin_comb(self.xb, xb1, self.λ)
        
    def after_fit(self): self.run.loss_func = self.old_loss_func
    
    def loss_func(self, pred, yb):
        if not self.in_train: return self.old_loss_func(pred, yb)
        with NoneReduce(self.old_loss_func) as loss_func:
            loss1 = loss_func(pred, yb)
            loss2 = loss_func(pred, self.yb1)
        loss = lin_comb(loss1, loss2, self.λ)
        return reduce_loss(loss, getattr(self.old_loss_func, 'reduction', 'mean'))



# +
lr = .001
pct_start = 0.5
phases = create_phases(pct_start)
sched_lr  = combine_scheds(phases, cos_1cycle_anneal(lr/10., lr, lr/1e5))
sched_mom = combine_scheds(phases, cos_1cycle_anneal(0.95, 0.85, 0.95))

cbfs = [
    partial(AvgStatsCallback,accuracy),
    partial(ParamScheduler, 'lr', sched_lr),
    partial(ParamScheduler, 'mom', sched_mom),
    partial(BatchTransformXCallback, norm_imagenette),
    ProgressCallback,
    Recorder,
    MixUp,
#     LR_Find,
    partial(CudaCallback, device)]

loss_func=LabelSmoothingCrossEntropy()
# arch = partial(xresnet34, n_classes)
arch = get_vision_model("resnet34", n_classes=n_classes, pretrained=True)

# opt_func = partial(sgd_mom_opt, wd=0.01)
opt_func = adam_opt(mom=0.9, mom_sqr=0.99, eps=1e-6, wd=1e-2)
# opt_func = lamb
# -

# # Training

clear_memory()

learn = Learner(arch,  data, loss_func, lr=lr, cb_funcs=cbfs, opt_func=opt_func)

learn.fit(1)

save_model(learn, "m1", fpath)

# +
temp = Path('/media/hdd/Datasets/ArtClass/Popular/artgerm/10004370_1657536534486515_1883801324_n.jpg')

get_class_pred(temp, learn ,ll, 128)
# -

temp = Path('/home/eragon/Downloads/Telegram Desktop/IMG_1800.PNG')

get_class_pred(temp, learn ,ll,128)

temp = Path('/home/eragon/Downloads/Telegram Desktop/IMG_20210106_180731.jpg')

get_class_pred(temp, learn ,ll,128)

# # Digging in

# +
# classification_report(learn, n_classes, device)
# -

learn.recorder.plot_lr()

learn.recorder.plot_loss()

# # Model vis

run_with_act_vis(1, learn)

# # Multiple runs with model saving

dict_runner = {
    "xres18":[1, partial(xresnet18, c_out=n_classes)(), data, loss_func, .001, cbfs,opt_func],
    "xres34":[1, partial(xresnet34, c_out=n_classes)(), data, loss_func, .001, cbfs,opt_func],
    "xres50":[1, partial(xresnet50, c_out=n_classes)(), data, loss_func, .001, cbfs,opt_func],
}

learn = Learner(arch(), data, loss_func, lr=lr, cb_funcs=cbfs, opt_func=opt_func)

multiple_runner(dict_runner, fpath)








