variable "aws_region" {
  description = "AWS Region"
  type        = string
  default     = "eu-central-1"
}

variable "instance_type" {
  description = "EC2 Instanztyp (t3.small: 2 vCPUs, 2 GB RAM, Free Tier eligible)"
  type        = string
  default     = "t3.small"
}

variable "ssh_public_key_path" {
  description = "Pfad zum lokalen SSH Public Key"
  type        = string
  default     = "~/.ssh/id_ed25519.pub"
}

variable "root_volume_size" {
  description = "Größe des gp3 Root-Volumes in GB"
  type        = number
  default     = 30
}

variable "override_allowed_cidr" {
  description = "Optionales manuelles Überschreiben der Admin-Ingress-CIDR für SSH/Web (Standard: dynamisch ermittelte eigene Public IP)"
  type        = string
  default     = null
}

variable "node_role" {
  description = "Rolle dieser Instanz: 'server' (Master / Control-Plane) oder 'agent' (Worker-Node)"
  type        = string
  default     = "server"
  validation {
    condition     = contains(["server", "agent"], var.node_role)
    error_message = "node_role muss entweder 'server' oder 'agent' sein."
  }
}

variable "server_url" {
  description = "K3s Server-URL des Master-Nodes (z. B. 'https://<MASTER_PUBLIC_IP>:6443'). Pflichtfeld bei node_role = 'agent'."
  type        = string
  default     = ""
}

variable "k3s_token" {
  description = "Pre-shared Secret Token für den K3s Cluster. Beim Master optional (wird sonst automatisch erzeugt), beim Worker erforderlich."
  type        = string
  default     = ""
  sensitive   = true
}

variable "node_name" {
  description = "Individueller Host- bzw. Node-Name im Kubernetes-Cluster (z. B. 'worker-alex'). Wenn leer, wird automatisch ein Name generiert."
  type        = string
  default     = ""
}

variable "k3s_api_allowed_cidrs" {
  description = "CIDR-Blöcke, die auf den K3s API-Server (Port 6443) zugreifen dürfen. Standard: 0.0.0.0/0 (gesichert durch K3s TLS & Token)."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}
