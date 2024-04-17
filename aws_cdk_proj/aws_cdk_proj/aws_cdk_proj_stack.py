from aws_cdk import (
    aws_ec2,
    aws_elasticloadbalancingv2 as elbv2,
    aws_iam as iam,
    CfnOutput,
    Stack
)
from constructs import Construct
class AwsLearnCdkStack(Stack):

    def __init__(self,  scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # 创建 VPC
        self.vpc = aws_ec2.Vpc(self, "MyVpc", max_azs=2)  # 最多使用两个可用区

        # 创建子网1
        subnet1 = aws_ec2.Subnet(self, "MySubnet1",
            vpc=self.vpc,
            cidr_block='10.0.0.0/24',
            availability_zone='ap-southeast-1a'
        )

        # 创建子网2
        subnet2 = aws_ec2.Subnet(self, "MySubnet2",
            vpc=self.vpc,
            cidr_block='10.0.1.0/24',
            availability_zone='ap-southeast-1b'
        )

        # 创建 EC2 实例1
        ec2_instance1 = aws_ec2.Instance(self, "MyInstance1",
            instance_type=aws_ec2.InstanceType.of(aws_ec2.InstanceClass.BURSTABLE2, aws_ec2.InstanceSize.MICRO),
            machine_image=aws_ec2.AmazonLinuxImage(),
            vpc=self.vpc,
            vpc_subnets=aws_ec2.SubnetSelection(subnets=[subnet1]),
        )
        # 启动 httpd 服务
        ec2_instance1.add_user_data("yum install -y httpd", "systemctl start httpd")

        # 创建 EC2 实例2
        ec2_instance2 = aws_ec2.Instance(self, "MyInstance2",
            instance_type=aws_ec2.InstanceType.of(aws_ec2.InstanceClass.BURSTABLE2, aws_ec2.InstanceSize.MICRO),
            machine_image=aws_ec2.AmazonLinuxImage(),
            vpc=self.vpc,
            vpc_subnets=aws_ec2.SubnetSelection(subnets=[subnet2]),
        )
        # 启动 httpd 服务
        ec2_instance2.add_user_data("sudo yum install -y httpd", "sudo systemctl start httpd")

        # 创建负载均衡器
        load_balancer = elbv2.ApplicationLoadBalancer(self, "MyLoadBalancer",
            vpc=self.vpc,
            internet_facing=True,
            load_balancer_name="my-load-balancer"
        )

        # 创建 Target Group1，并添加 EC2 实例1
        target_group1 = elbv2.ApplicationTargetGroup(self, "MyTargetGroup1",
            vpc=self.vpc,
            port=80,
            targets=[ec2_instance1],
            target_group_name="myTargetGroup1"
        )

        # 创建 Target Group2，并添加 EC2 实例2
        target_group2 = elbv2.ApplicationTargetGroup(self, "MyTargetGroup2",
            vpc=self.vpc,
            port=80,
            targets=[ec2_instance2],
            target_group_name="myTargetGroup2"
        )

        # 添加 Listener，并将 Target Group1 和 Target Group2 关联
        listener = load_balancer.add_listener("MyListener", port=80)
        listener.add_targets("MyTargetGroup1", port=80, targets=[ec2_instance1])
        listener.add_targets("MyTargetGroup2", port=80, targets=[ec2_instance2])

        # 输出负载均衡器的 DNS 名称
        CfnOutput(self, "LoadBalancerDNS",
            value=load_balancer.load_balancer_dns_name
        )
