import os
import boto3
import paramiko
import time

region = 'ap-southeast-2'
sub_cidrBlocks = ['172.31.8.0/28', '172.31.9.0/28']
ssh_username = 'ec2-user'  # SSH 用户名
ssh_key_path = 'D:\Download\genKey\EC2asOpenSSH'  # 私钥文件路径

class EC2Ops():
    # 获取EC2 Session
    def __init__(self, region):
        self.region = region
        self.ec2 = boto3.client('ec2', region_name=self.region)
        self.getVpcInfo()
        self.getAvailableZones()
        self.getSKPair()
        self.getSecurityGroup()
        # des = ec2.describe_instances()
        # for i in des.keys():
        #     print(i, des[i])
        #     if type(des[i]) == list:
        #         for j in range(len(des[i])):
        #             if isinstance(des[i][j], dict):
        #                 print("OwnerId", des[i][j]['OwnerId'])
        #                 instances = des[i][j]['Instances']
        #                 for k in range(len(instances)):
        #                     print('Tag', instances[k]['Tags'][0]['Value'])
        #                     print('Instance', instances[k])
        #                     print('ImageId', instances[k]['ImageId'])
        #                     print('InstanceId', instances[k]['InstanceId'])
        #                     print('LaunchTime', instances[k]['LaunchTime'])
        #                     print('Monitoring', instances[k]['Monitoring'])
        #                     print('State', instances[k]['State']['Name'])
        #                     print('AvailabilityZone', instances[k]['Placement']['AvailabilityZone'])
        #                     print('SecurityGroups', instances[k]['SecurityGroups'])

    def getVpcInfo(self):
        vpcs = self.ec2.describe_vpcs()
        self.vpc_id = vpcs['Vpcs'][0]['VpcId']  # 拿到vpcid
        self.vpc_block = vpcs['Vpcs'][0]['CidrBlock']


    def getAvailableZones(self):
        availability_zones = self.ec2.describe_availability_zones()['AvailabilityZones']
        self.a_zones = []
        for i in range(len(availability_zones)):
            print(availability_zones[i]['ZoneName'], 'ZoneId:', availability_zones[i]['ZoneId'])  # 获得所有可用中心
            self.a_zones.append(availability_zones[i]['ZoneName'])
        print(self.a_zones)


    def getSKPair(self):
        # 获取所有密钥对
        response = self.ec2.describe_key_pairs()
        self.sk_pairlst = []
        # 打印所有密钥对
        for key_pair in response['KeyPairs']:
            key_name = key_pair['KeyName']
            print("Key Pair Name:", key_name)
            self.sk_pairlst.append(key_name)


    def getSecurityGroup(self):
        # 获取所有安全组
        response = self.ec2.describe_security_groups(
            Filters = [
                {'Name': 'group-name',
                 'Values': ['MyInstanceSG']
                }
            ]
        )
        self.sec_group_id = response['SecurityGroups'][0]['GroupId']

    # 根据状态获取EC2实例ids
    def getEC2InstanceIdsByStatus(self, status):
        # 获取特定状态的实例
        response = self.ec2.describe_instances(
            Filters = [
                {
                    'Name': 'instance-state-name',
                    'Values': [status]
                }
            ]
        )

        lst = []
        # 打印特定状态的实例的 ID
        for reservation in response['Reservations']:
            for instance in reservation['Instances']:
                instance_id = instance['InstanceId']
                print(f"{status} Instance ID:", instance_id)
                lst.append(instance_id)
        return lst

    # 根据EC2实例id列表停止实例
    def stopEC2Instance(self, instance_ids):
        response = self.ec2.stop_instances(InstanceIds=instance_ids)
        for instance in response['StoppingInstances']:
            print(f"Instance {instance['InstanceId']} is {instance['CurrentState']['Name']}")

    # 根据EC2实例id列表删除实例
    def deleteEC2Instance(self, instance_ids):
        response = self.ec2.terminate_instances(InstanceIds=instance_ids)
        for instance in response['TerminatingInstances']:
            print(f"Instance {instance['InstanceId']} is {instance['CurrentState']['Name']}")


    def getMyAMIIDByName(self, ami_name):
        # 获取特定名称的 AMI
        response = self.ec2.describe_images(
            Owners = ['self'],  # 只查找自己的 AMI
            Filters = [
                {'Name': 'name',
                 'Values': [ami_name]
                }
            ]
        )
        return response['Images'][0]['ImageId']


    def createSubnet(self, a_zone, sub_cidrBlock, index):
        # 获取internet网关
        igw_response = self.ec2.describe_internet_gateways()
        igw_id = igw_response['InternetGateways'][0]['InternetGatewayId']
        route_table_response = self.ec2.create_route_table(
            VpcId = self.vpc_id
        )
        route_table_id = route_table_response['RouteTable']['RouteTableId']

        self.ec2.create_route(
            DestinationCidrBlock='0.0.0.0/0',
            GatewayId = igw_id,
            RouteTableId = route_table_id
        )
        response = self.ec2.create_subnet(
            VpcId=self.vpc_id,
            CidrBlock=sub_cidrBlock,  # 子网的 CIDR 块
            AvailabilityZone=a_zone,  # 子网的可用区
            TagSpecifications=[
                {
                    'ResourceType': 'subnet',
                    'Tags': [
                        {
                            'Key': 'Name',
                            'Value': 'private_subnet' + str(index)
                        }
                    ]
                }
            ]
        )
        print("Created subnet:", response['Subnet']['SubnetId'])
        self.ec2.associate_route_table(
            SubnetId = response['Subnet']['SubnetId'],
            RouteTableId = route_table_id
        )
        return response['Subnet']['SubnetId']


    def getSubNetIdByCidrBlock(self, sub_cidrBlock):
        # 获取子网信息
        response = self.ec2.describe_subnets(Filters=[{'Name': 'cidrBlock', 'Values': [sub_cidrBlock]}])

        # 提取子网 ID
        return response['Subnets'][0]['SubnetId']


    def createEC2Instances(self, subnet_id, instance_num, ami_id='ami-0035ee596a0a12a7b'):
        # ami_id = self.getMyAMIIDByName('EC2_httpd')
        # 定义启动两个 EC2 实例的参数
        instance_params = {
            'ImageId': ami_id,  # AMI ID
            'InstanceType': 't2.micro',  # 实例类型
            'KeyName': self.sk_pairlst[0],  # 密钥对名称
            'MaxCount': instance_num,  # 创建两个实例
            'MinCount': instance_num,  # 最少两个实例
            'NetworkInterfaces': [
                {
                    'AssociatePublicIpAddress': True,
                    'DeviceIndex': 0,
                    'Groups': [self.sec_group_id],  # 安全组ID列表
                    'SubnetId': subnet_id,  # 子网 ID
                }
            ]
        }

        # 启动两个 EC2 实例
        response = self.ec2.run_instances(**instance_params)

        # 获取新创建实例的 ID
        instance_ids = [instance['InstanceId'] for instance in response['Instances']]
        print("Created instances:", instance_ids)
        return instance_ids


    def getPublicIPs(self, instance_ids):
        # 等待实例运行
        self.ec2.get_waiter('instance_running').wait(InstanceIds=instance_ids)

        # 获取实例的公共 IP 地址
        response = self.ec2.describe_instances(InstanceIds=instance_ids)
        public_ips = [instance['PublicIpAddress'] for reservation in response['Reservations']
                      for instance in reservation['Instances']]
        print("Public IPs of instances:", public_ips)
        return public_ips


    # SSH 连接函数
    def ssh_connect(self, ip, username, ssh_key_path, timeout=10):
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(ip, username=username, key_filename=ssh_key_path, timeout=timeout)
        return ssh


    def startService(self, ips):
        # 在每个实例上启动 httpd 服务
        for ip in ips:
            ssh = self.ssh_connect(ip, ssh_username, ssh_key_path)
            file_content = "hello\n"
            cmd_lst = ['sudo yum install -y httpd',
                       'sudo systemctl start httpd',
                       'sudo touch /var/www/html/index.html',
                       f"echo '{file_content}' | sudo tee /var/www/html/index.html",
                       'sudo systemctl restart httpd',
                       'sudo systemctl enable httpd']
            for i in range(len(cmd_lst)):
                stdin, stdout, stderr = ssh.exec_command(cmd_lst[i], timeout=10)
                error = stderr.read().decode('utf-8')
                if error:
                    print(i, "Error :", error)
                    return
            ssh.close()


    def createLoadBalancer(self, instance_ids):
        # 创建 ELB 客户端
        elbv2 = boto3.client('elbv2', region_name=self.region)

        # 创建目标组
        target_group_response = elbv2.create_target_group(
            Name = 'ec2-httpd-group',
            Protocol = 'HTTP',  # 目标组的协议
            Port = 80,  # 目标组的端口
            VpcId = self.vpc_id,  # 目标组的 VPC ID
            TargetType = 'instance',  # 目标组的目标类型
        )

        # 获取新创建目标组的 ARN
        target_group_arn = target_group_response['TargetGroups'][0]['TargetGroupArn']
        print("Created Target Group:", target_group_arn)

        # 将实例添加到目标组
        for instance_id in instance_ids:
            elbv2.register_targets(
                TargetGroupArn = target_group_arn,
                Targets = [{'Id': instance_id}]
            )
            print("Added instance", instance_id, "to Target Group")

        subnets = self.ec2.describe_subnets(Filters = [{'Name': 'vpc-id', 'Values': [self.vpc_id]}])['Subnets']
        subnet1_id = subnets[0]['SubnetId']
        subnet2_id = subnets[1]['SubnetId']

        # 创建负载均衡器
        elb_response = elbv2.create_load_balancer(
            Name = 'webApp-load-balance',
            Subnets = [subnet1_id, subnet2_id],  # 负载均衡器的子网 ID
            SecurityGroups = [self.sec_group_id],  # 负载均衡器的安全组 ID
            Scheme = 'internet-facing',  # 负载均衡器的访问方案
            Type = 'application',  # 负载均衡器的类型
            IpAddressType = 'ipv4'  # 负载均衡器的 IP 地址类型
        )

        # 获取新创建负载均衡器的 ARN
        elb_arn = elb_response['LoadBalancers'][0]['LoadBalancerArn']
        elb_dns = elb_response['LoadBalancers'][0]['DNSName']
        print("Created ELB:", elb_arn)

        # 创建监听器，并将目标组与监听器关联
        listener_response = elbv2.create_listener(
            LoadBalancerArn = elb_arn,
            Protocol = 'HTTP',
            Port = 80,
            DefaultActions = [{
                'Type': 'forward',
                'TargetGroupArn': target_group_arn
            }]
        )
        print("Created Listener:", listener_response['Listeners'][0]['ListenerArn'], elb_dns)


if __name__ == '__main__':

    ec2_ops = EC2Ops(region)

    for i in range(2):
        # 创建子网
        subnet_id = ec2_ops.createSubnet(ec2_ops.a_zones[i], sub_cidrBlocks[i], i + 1)
        # 根据子网块获取子网id
        # subnet_id = ec2_ops.getSubNetIdByCidrBlock(sub_cidrBlocks[i])
        # 创建实例后返回实例id
        instance_ids = ec2_ops.createEC2Instances(subnet_id, 2)
        # # 根据实例id返回实例公网ip
        public_ips = ec2_ops.getPublicIPs(instance_ids)
        # # 启动httpd服务
        ec2_ops.startService(public_ips)
    # 根据运行状态返回实例id
    instance_ids = ec2_ops.getEC2InstanceIdsByStatus('running')
    # 创建load balancer
    ec2_ops.createLoadBalancer(instance_ids)
