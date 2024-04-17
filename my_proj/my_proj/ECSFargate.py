from aws_cdk import (
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_ecr as ecr,
    aws_elasticloadbalancingv2 as elbv2,
    aws_logs as logs,
    # aws_iam as iam,
    # aws_autoscaling as autoscaling,
    # aws_fargate as fargate
)
import aws_cdk as core
from constructs import Construct

class EcsFargateStack(core.Stack):

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # 创建 VPC 和子网
        self.vpc = ec2.Vpc(
            self, "MyVpc",
            max_azs=2,
            nat_gateways=1
        )

        # 创建 ECR 存储库
        ecr_repository = ecr.Repository(
            self, "MyECRRepository",
            removal_policy=core.RemovalPolicy.DESTROY
        )

        # 定义 ECS 集群
        cluster = ecs.Cluster(
            self, "MyCluster",
            vpc=self.vpc
        )

        # 创建 ECS Task Definition
        task_definition = ecs.FargateTaskDefinition(
            self, "MyTaskDefinition",
        )

        # 添加容器到 Task Definition
        container = task_definition.add_container(
            "MyContainer",
            image=ecs.ContainerImage.from_ecr_repository(ecr_repository),
            memory_limit_mib=256,
            cpu=256,
            logging=ecs.AwsLogDriver(
                stream_prefix="MyContainer",
                log_group=logs.LogGroup(
                    self, "MyLogGroup",
                    log_group_name="MyLogGroup",
                    removal_policy=core.RemovalPolicy.DESTROY
                )
            )
        )
        # 明确指定容器的端口映射
        container.add_port_mappings(
            ecs.PortMapping(container_port=80)
        )

        # 创建 ECS Service
        service = ecs.FargateService(
            self, "MyFargateService",
            cluster=cluster,
            task_definition=task_definition
        )

        # 添加 AutoScaling
        scaling = service.auto_scale_task_count(
            min_capacity=1,
            max_capacity=2
        )

        # 创建 Application Load Balancer
        alb = elbv2.ApplicationLoadBalancer(
            self, "MyALB",
            vpc=self.vpc,
            internet_facing=True
        )

        # 添加 Target Group
        target_group = elbv2.ApplicationTargetGroup(
            self, "MyTargetGroup",
            vpc=self.vpc,
            port=80,
            targets=[service]
        )

        # 添加 Listener，并将 Target Group 关联
        listener = alb.add_listener(
            "MyListener",
            port=80,
            open=True,
            default_target_groups=[target_group]
        )

        # 输出 ALB DNS 名称
        output = core.CfnOutput(
            self, "MyALBDNS",
            value=alb.load_balancer_dns_name
        )


