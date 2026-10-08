output "instance_role" {
  description = "Rolle dieser Node-Instanz (server oder agent)"
  value       = var.node_role
}

output "node_name" {
  description = "Name dieser Node im Kubernetes Cluster"
  value       = local.node_name
}

output "instance_public_ip" {
  description = "Oeffentliche IP-Adresse der EC2-Instanz"
  value       = aws_instance.k3s_node.public_ip
}

output "instance_private_ip" {
  description = "Private IP-Adresse der EC2-Instanz"
  value       = aws_instance.k3s_node.private_ip
}

output "ssh_login_command" {
  description = "Direkter SSH-Verbindungsbefehl zur EC2-Instanz"
  value       = "ssh -i ${var.ssh_public_key_path != "~/.ssh/id_ed25519.pub" ? replace(var.ssh_public_key_path, ".pub", "") : "~/.ssh/id_ed25519"} ubuntu@${aws_instance.k3s_node.public_ip}"
}

output "bootstrap_status_command" {
  description = "Befehl zum Live-Verfolgen des K3s Bootstrap-Logs"
  value       = "ssh ubuntu@${aws_instance.k3s_node.public_ip} \"tail -f /var/log/bootstrap-cluster.log\""
}

# --- Ausgaben fuer den Master (server) ---

output "k3s_server_url" {
  description = "K3s Server-URL fuer Worker-Nodes (nur relevant fuer Master)"
  value       = var.node_role == "server" ? "https://${aws_instance.k3s_node.public_ip}:6443" : "N/A (Agent Node)"
}

output "k3s_token" {
  description = "K3s Join-Token fuer das Multinode-Cluster (an Worker weitergeben)"
  value       = var.node_role == "server" ? nonsensitive(local.k3s_token) : "N/A (Agent Node)"
}

output "worker_terraform_apply_command" {
  description = "Befehl, den die Kollegen auf ihren Rechnern ausfuehren koennen, um als Worker beizutreten"
  value       = var.node_role == "server" ? "terraform apply -var=\"node_role=agent\" -var=\"server_url=https://${aws_instance.k3s_node.public_ip}:6443\" -var=\"k3s_token=${nonsensitive(local.k3s_token)}\" -var=\"node_name=worker-$(whoami)\"" : "N/A"
}

output "worker_tfvars_snippet" {
  description = "Inhalt fuer die terraform.tfvars-Datei der Worker"
  value       = var.node_role == "server" ? format(
    "\nnode_role  = \"agent\"\nserver_url = \"https://%s:6443\"\nk3s_token  = \"%s\"\nnode_name  = \"worker-NAME\"\n",
    aws_instance.k3s_node.public_ip,
    nonsensitive(local.k3s_token)
  ) : "N/A"
}

output "kubeconfig_fetch_command" {
  description = "Befehl zum Herunterladen der Kubeconfig fuer lokalen kubectl-Zugriff"
  value       = var.node_role == "server" ? "ssh ubuntu@${aws_instance.k3s_node.public_ip} \"sudo cat /etc/rancher/k3s/k3s.yaml\" | sed 's/127.0.0.1/${aws_instance.k3s_node.public_ip}/g' > kubeconfig-k3s.yaml" : "N/A"
}
