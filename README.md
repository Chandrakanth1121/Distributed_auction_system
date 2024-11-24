# Instructions

## Deploying database servers locally
#### Step 1 : Start docker desktop
#### Step 2 : Enable kubernetes (https://docs.docker.com/desktop/features/kubernetes/)
#### Step 3 : Run `kubectl apply -f kubernetes/database-ns` to deploy kubernetes services and deployments.
#### Step 4 : Verify if the database pods are running by running the command `kubectl get pods -n database`.


## Database command examples:
#### Add record : 
```
curl -X POST -H "Content-Type: application/json" -d '{"key": "1", "record": {"name": "Alice", "age": 25}}' http://127.0.0.1:5000/records
```
#### Update record with key=1: 
```
curl -X PUT -H "Content-Type: application/json" -d '{"name": "Alice_updated", "age": 25}' http://127.0.0.1:5000/records/1
```
#### Delete record with key=1: 
```
curl -X DELETE http://127.0.0.1:5000/records/1
```
#### Get record with key=1
```
curl -X GET http://10.1.0.6:5000/records/1
```
#### Get all records
```
curl -X GET http://10.1.0.6:5000/records
```
