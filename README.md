# Instructions

## Connect to the GKE cluster
#### Step 1 : Get kubectl context (you must be authenticated to gcloud): 
```
gcloud container clusters get-credentials main-gke --zone us-central1-c --project grounded-pilot-443304-t6
```
#### Step 2 : Verify if the database pods are running by running the command `kubectl get pods -n database`.


## Endpoint
http://auctionapp.final-project.live/
