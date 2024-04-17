#!/usr/bin/env python3
import os

import aws_cdk as cdk

from aws_cdk_proj.aws_cdk_proj_stack import AwsLearnCdkStack


app = cdk.App()
AwsLearnCdkStack(app, "AwsLearnCdkStack",)

app.synth()
