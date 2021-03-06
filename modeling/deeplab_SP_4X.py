import torch
import torch.nn as nn
import torch.nn.functional as F
from modeling.sync_batchnorm.batchnorm import SynchronizedBatchNorm2d
from modeling.aspp import build_aspp
from modeling.decoder import build_decoder
from modeling.backbone import build_backbone
from modeling.sr_decoder import build_sr_decoder
from modeling.deeplab import EDSRConv

import matplotlib.pyplot as plt
import numpy as np

class DeepLab_SP_4x(nn.Module):
    def __init__(self, backbone='resnet', output_stride=16, num_classes=21,
                 sync_bn=True, freeze_bn=False, SR=4):
        super(DeepLab_SP_4x, self).__init__()

        self.SR = SR
        if backbone == 'drn':
            output_stride = 8

        if sync_bn == True:
            BatchNorm = SynchronizedBatchNorm2d
        else:
            BatchNorm = nn.BatchNorm2d

        self.backbone = build_backbone(backbone, output_stride, BatchNorm)
        self.aspp = build_aspp(backbone, output_stride, BatchNorm)
        self.decoder = build_decoder(num_classes, backbone, BatchNorm)
        self.sr_decoder = build_sr_decoder(num_classes, backbone, BatchNorm)
        self.pointwise = torch.nn.Sequential(
            torch.nn.Conv2d(num_classes, 3, 1),
            torch.nn.BatchNorm2d(3),  # 添加了BN层
            torch.nn.ReLU(inplace=True)
        )

        self.sr_conv = torch.nn.Sequential(
            torch.nn.Conv2d(64, 64, 5, 1, 2),
            torch.nn.Tanh(),
            torch.nn.Conv2d(64, 32, 3, 1, 1),
            torch.nn.Tanh(),
            torch.nn.Conv2d(32, 3*self.SR**2, 3, 1, 1),
            torch.nn.PixelShuffle(self.SR),
            # torch.nn.Sigmoid()
        )

        self.freeze_bn = freeze_bn

    def forward(self, input):
        x, low_level_feat = self.backbone(input)
        x = self.aspp(x)
        x_seg = self.decoder(x, low_level_feat)
        x_sr = self.sr_decoder(x, low_level_feat)
        x_seg_up = F.interpolate(x_seg, size=input.size()[2:], mode='bilinear', align_corners=True)
        x_seg_up = F.interpolate(x_seg_up, size=[self.SR * i for i in input.size()[2:]], mode='bilinear', align_corners=True)

        x_sr_up = F.interpolate(x_sr, size=input.size()[2:], mode='bilinear', align_corners=True)
        x_sr_up = self.sr_conv(x_sr_up)

        return x_seg_up, x_sr_up, self.pointwise(x_seg_up), x_sr_up

    def freeze_bn(self):
        for m in self.modules():
            if isinstance(m, SynchronizedBatchNorm2d):
                m.eval()
            elif isinstance(m, nn.BatchNorm2d):
                m.eval()

    def get_1x_lr_params(self):
        modules = [self.backbone]
        for i in range(len(modules)):
            for m in modules[i].named_modules():
                if self.freeze_bn:
                    if isinstance(m[1], nn.Conv2d):
                        for p in m[1].parameters():
                            if p.requires_grad:
                                yield p
                else:
                    if isinstance(m[1], nn.Conv2d) or isinstance(m[1], SynchronizedBatchNorm2d) \
                            or isinstance(m[1], nn.BatchNorm2d):
                        for p in m[1].parameters():
                            if p.requires_grad:
                                yield p

    def get_10x_lr_params(self):
        modules = [self.aspp, self.decoder]
        for i in range(len(modules)):
            for m in modules[i].named_modules():
                if self.freeze_bn:
                    if isinstance(m[1], nn.Conv2d):
                        for p in m[1].parameters():
                            if p.requires_grad:
                                yield p
                else:
                    if isinstance(m[1], nn.Conv2d) or isinstance(m[1], SynchronizedBatchNorm2d) \
                            or isinstance(m[1], nn.BatchNorm2d):
                        for p in m[1].parameters():
                            if p.requires_grad:
                                yield p


if __name__ == "__main__":
    model = DeepLab(backbone='mobilenet', output_stride=16)
    model.eval()
    input = torch.rand(1, 3, 512, 512)
    output = model(input)


