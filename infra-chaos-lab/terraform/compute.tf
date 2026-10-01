# Neuestes offizielles Ubuntu 24.04 LTS (Noble Numbat) AMI von Canonical
data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"]

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd*ubuntu-noble-24.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# Lokaler SSH Public Key
resource "aws_key_pair" "lab_key" {
  key_name   = "messframework-ssh-key"
  public_key = file(pathexpand(var.ssh_public_key_path))
}

# EC2 Single-Node K3s Instanz (t3.medium: 2 vCPUs, 4 GB RAM)
resource "aws_instance" "k3s_node" {
  ami                         = data.aws_ami.ubuntu.id
  instance_type               = var.instance_type
  key_name                    = aws_key_pair.lab_key.key_name
  subnet_id                   = aws_subnet.public.id
  vpc_security_group_ids      = [aws_security_group.k3s_node_sg.id]
  associate_public_ip_address = true

  root_block_device {
    volume_size           = var.root_volume_size
    volume_type           = "gp3"
    delete_on_termination = true
    encrypted             = true

    tags = {
      Name = "messframework-k3s-root-vol"
    }
  }

  user_data = file("${path.module}/cloud-init.yaml")

  tags = {
    Name = "messframework-k3s-node"
  }
}
