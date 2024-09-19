docker build -t dicomfix-webapp -f docker/Dockerfile .
docker run -p 8501:8501 dicomfix-webapp

# To export to systems with no www access
docker save -o dicomfix-webapp.tar dicomfix-webapp
scp dicomfix-webapp.tar xxx@xxx:/xxx


On remote system:
docker load -i ./dicomfix-webapp.tar
docker run -p 8501:8501 dicomfix-webapp