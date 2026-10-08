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

# Eindeutiger Suffix für Hostnamen & Ressourcen, um Namenskonflikte zu vermeiden
resource "random_string" "node_suffix" {
  length  = 4
  special = false
  upper   = false
}

# Zufälliger Token für K3s Cluster, falls beim Server nicht manuell vorgegeben
resource "random_password" "k3s_token" {
  length  = 48
  special = false
}

locals {
  default_name = var.node_role == "server" ? "k3s-master" : "k3s-worker-${random_string.node_suffix.result}"
  node_name    = var.node_name != "" ? var.node_name : local.default_name
  k3s_token    = var.k3s_token != "" ? var.k3s_token : random_password.k3s_token.result
}

# Lokaler SSH Public Key (mit Präfix gegen Kollisionen in geteilten AWS Accounts)
resource "aws_key_pair" "lab_key" {
  key_name_prefix = "k3s-key-${local.node_name}-"
  public_key      = file(pathexpand(var.ssh_public_key_path))
}

# Prüfung der Pflichtangaben für Worker
check "worker_configuration_check" {
  assert {
    condition     = var.node_role == "server" || (var.server_url != "" && var.k3s_token != "")
    error_message = "Fuer einen Worker (node_role = 'agent') muessen 'server_url' (z. B. 'https://<MASTER_PUBLIC_IP>:6443') und 'k3s_token' in terraform.tfvars oder als -var angegeben werden!"
  }
}

# EC2 K3s Instanz (Server oder Agent)
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
      Name = "k3s-${local.node_name}-root-vol"
    }
  }

  user_data = templatefile("${path.module}/cloud-init.yaml.tftpl", {
    node_role  = var.node_role
    node_name  = local.node_name
    k3s_token  = local.k3s_token
    server_url = var.server_url
  })

  tags = {
    Name = "k3s-${local.node_name}"
    Role = var.node_role
  }
}
