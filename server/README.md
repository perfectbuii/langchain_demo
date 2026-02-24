# Start
cd server && go run .

# HTTP examples
```sh
curl -X POST http://localhost:8080/accounts \
  -H "Content-Type: application/json" \
  -d '{"name":"Alice","email":"alice@example.com"}'

curl http://localhost:8080/accounts/<id>
curl http://localhost:8080/accounts
```

# gRPC (grpcurl)
```sh
grpcurl -plaintext -d '{"name":"Bob","email":"bob@example.com"}' \
  localhost:9090 account.AccountService/CreateAccount
grpcurl -plaintext -d '{"id":"<id>"}' \
  localhost:9090 account.AccountService/GetAccount
grpcurl -plaintext localhost:9090 account.AccountService/ListAccounts
```