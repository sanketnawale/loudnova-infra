$ErrorActionPreference = "Stop"
kubectl delete -k .\clusters\loudnova\apps\hello-web\overlays\home --ignore-not-found