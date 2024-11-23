```
sudo docker build -t dicomfix-webapp -f docker/Dockerfile .
sudo docker run -p 8501:8501 dicomfix-webapp
```
To export to systems with no www access
```
sudo docker save -o dicomfix-webapp.tar dicomfix-webapp
sudo chown xxx:xxx dicomfix-webapp.tar
scp dicomfix-webapp.tar xxx@xxx:/xxx
```

On remote system:
```
docker load -i ./dicomfix-webapp.tar
# HTTP version:
docker run -p 8501:8501 dicomfix-webapp  # will overwrite any existing :latest image

# HTTPS version:
docker run -p 8443:8443 -e SSL_CERT_FILE=/etc/ssl/certs/dicomfix.crt -e SSL_KEY_FILE=/etc/ssl/private/dicomfix.key dicomfix-webapp:latest
```
