# Ermittelt dynamisch deine reale öffentliche WAN-IP beim terraform apply
data "http" "my_public_ip" {
  url = "https://checkip.amazonaws.com"
}

locals {
  detected_ip  = chomp(data.http.my_public_ip.response_body)
  allowed_cidr = var.override_allowed_cidr != null ? var.override_allowed_cidr : "${local.detected_ip}/32"
}

resource "aws_security_group" "k3s_node_sg" {
  name_prefix = "k3s-sg-${local.node_name}-"
  description = "Security Group fuer K3s Node (${local.node_name})"
  vpc_id      = aws_vpc.main.id

  # SSH-Zugriff (von ueberall erreichbar, durch SSH Private Key geschuetzt)
  ingress {
    description = "SSH from anywhere"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # Cluster-interner Traffic zwischen K3s Nodes (wenn in gleicher SG / VPC)
  ingress {
    description = "K3s inter-node traffic (Security Group)"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    self        = true
  }

  ingress {
    description = "K3s inter-node traffic (VPC CIDR)"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = [aws_vpc.main.cidr_block]
  }

  # K3s Kubernetes API Server (Worker muessen den Master erreichen koennen)
  ingress {
    description = "K3s Kubernetes API Server"
    from_port   = 6443
    to_port     = 6443
    protocol    = "tcp"
    cidr_blocks = var.k3s_api_allowed_cidrs
  }

  # WireGuard Pod-Netzwerk-Tunnel (fuer clusterweites Pod-to-Pod Routing ueber Public IPs)
  ingress {
    description = "Flannel WireGuard Pod Network Overlay"
    from_port   = 51820
    to_port     = 51820
    protocol    = "udp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # Kubelet API (wichtig fuer kubectl logs & exec vom Master auf Worker-Pods)
  ingress {
    description = "Kubelet API (Logs / Exec)"
    from_port   = 10250
    to_port     = 10250
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # HTTP / HTTPS (fuer Ingress-Controller / Web-Workloads)
  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # K8s NodePort Range (z. B. Casting-Web-UI auf Port 30040)
  ingress {
    description = "K8s NodePort Services"
    from_port   = 30000
    to_port     = 32767
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # Vollstaendiger Egress
  egress {
    from_port        = 0
    to_port          = 0
    protocol         = "-1"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }

  tags = {
    Name = "k3s-${local.node_name}-sg"
  }
}
