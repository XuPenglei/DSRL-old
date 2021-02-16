import torch
import torch.nn as nn
import torch.nn.functional as F
from modeling.sync_batchnorm.batchnorm import SynchronizedBatchNorm2d
from modeling.aspp import build_aspp
from modeling.decoder import build_decoder
from modeling.backbone import build_backbone
from modeling.sr_decoder import build_sr_decoder
from modeling.deeplab import EDSRConv


class DeepLab_4X(nn.Module):
    def __init__(self, backbone='resnet', output_stride=16, num_classes=21,
                 sync_bn=True, freeze_bn=False):
        super(DeepLab_4X, self).__init__()
        if backbone == 'drn':
            output_stride = 8

        if sync_bn == True:
            BatchNorm = SynchronizedBatchNorm2d
        else:
            BatchNorm = nn.BatchNorm2d

        self.backbone = build_backbone(backbone, output_stride, BatchNorm)
        self.aspp = build_aspp(backbone, output_stride, BatchNorm)
        self.decoder = build_decoder(num_classes, backbone, BatchNorm)
        self.sr_decoder = build_sr_decoder(num_classes,backbone,BatchNorm)
        self.pointwise = torch.nn.Sequential(
            torch.nn.Conv2d(num_classes,3,1),
            torch.nn.BatchNorm2d(3),  #添加了BN层
            torch.nn.ReLU(inplace=True)
        )

        self.up_sr_1 = nn.ConvTranspose2d(64, 64, 2, stride=2) 
        self.up_edsr_1 = EDSRConv(64,64)
        self.up_sr_2 = nn.ConvTranspose2d(64, 32, 2, stride=2) 
        self.up_edsr_2 = EDSRConv(32,32)
        self.up_sr_3 = nn.ConvTranspose2d(32, 16, 2, stride=2) 
        self.up_edsr_3 = EDSRConv(16,16)
        self.up_sr_4 = nn.ConvTranspose2d(16, 8, 2, stride=2)
        self.up_edsr_4 = EDSRConv(8, 8)
        self.up_conv_last = nn.Conv2d(8,3,1)


        self.freeze_bn = freeze_bn

    def forward(self, input):
        x, low_level_feat = self.backbone(input)
        x = self.aspp(x)
        x_seg = self.decoder(x, low_level_feat)
        x_sr= self.sr_decoder(x, low_level_feat)
        x_seg_up = F.interpolate(x_seg, size=input.size()[2:], mode='bilinear', align_corners=True)
        x_seg_up = F.interpolate(x_seg_up,size=[2*i for i in input.size()[2:]], mode='bilinear', align_corners=True)
        x_seg_up = F.interpolate(x_seg_up,size=[4*i for i in input.size()[2:]], mode='bilinear', align_corners=True)


        x_sr_up = self.up_sr_1(x_sr)
        x_sr_up=self.up_edsr_1(x_sr_up)

        x_sr_up = self.up_sr_2(x_sr_up)
        x_sr_up=self.up_edsr_2(x_sr_up)

        x_sr_up = self.up_sr_3(x_sr_up)
        x_sr_up=self.up_edsr_3(x_sr_up)

        x_sr_up = self.up_sr_4(x_sr_up)
        x_sr_up = self.up_edsr_4(x_sr_up)
        x_sr_up=self.up_conv_last(x_sr_up)

        return x_seg_up,x_sr_up,self.pointwise(x_seg_up),x_sr_up

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
    model = DeepLab_4X(backbone='mobilenet', output_stride=16)
    model.eval()
    input = torch.rand(1, 3, 512, 512)
    output = model(input)
    print(output.size())


