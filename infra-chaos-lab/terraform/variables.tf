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
  description = "Optionales manuelles Überschreiben der Ingress-CIDR (Standard: dynamisch ermittelte eigene Public IP)"
  type        = string
  default     = null
}
