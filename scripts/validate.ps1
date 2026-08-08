$ErrorActionPreference = "Stop"
$expectedContext = "loudnova-home"
$currentContext = kubectl config current-context
if ($currentContext -ne $expectedContext) { throw "Wrong Kubernetes context: $currentContext. Expected: $expectedContext" }
kubectl get nodes
kubectl kustomize .\clusters\loudnova\platform | Out-Null
kubectl kustomize .\clusters\loudnova\apps\hello-web\overlays\home | Out-Null
kubectl apply -k .\clusters\loudnova\apps\hello-web\overlays\home --dry-run=server
Write-Host "Validation completed successfully."