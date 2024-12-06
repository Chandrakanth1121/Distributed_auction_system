# Endpoint
http://auctionapp.final-project.live/

# Instructions to deploy and configure kubernetes

## Build Docker images:
### Auction-service:
```
docker build -t auction-service docker_images/auction
```
### Database service:
```
docker build -t database-image docker_images/database
```

## Connect to the GKE cluster
#### Step 1 : Get kubectl context (you must be authenticated to gcloud): 
```
gcloud container clusters get-credentials main-gke --zone us-central1-c --project grounded-pilot-443304-t6
```


## Apply k8s config
#### Step 1 : Apply kubernetes config files to the cluster
```
kubectl apply -f kubernetes/auction-service-ns
kubectl apply -f kubernetes/database-ns
```
#### Step 2 : Verify if the pods are running by running the command 
```
kubectl get pods -n database
kubectl get pods -n auction-service
```
#### Step 3 : Get the auction service endpoint
```
kubectl get svc -o wide -n auction-service
NAME                       TYPE           CLUSTER-IP      EXTERNAL-IP      PORT(S)        AGE     SELECTOR
auction-service-external   LoadBalancer   34.118.225.96   35.222.184.139   80:32380/TCP   5d13h   app=auction-service
```
#### Step 4 : Create a DNS record
Create a DNS record in GCP to route the endpoint URL to the EXTERNAL-IP shown in the last step

#### Step 5 : Check logs to verify that the algorithms are working as expected
```
kubectl logs -f <database pod> -n database
```
