package handler

import (
	"context"
	"errors"

	pb "github.com/haobuihoan/account-server/proto/account"
	"github.com/haobuihoan/account-server/service"
	"github.com/haobuihoan/account-server/store"
	"google.golang.org/grpc/codes"
	grpcstatus "google.golang.org/grpc/status"
)

// AccountGRPCHandler implements the gRPC AccountServiceServer interface.
type AccountGRPCHandler struct {
	pb.UnimplementedAccountServiceServer
	svc *service.AccountService
}

// NewAccountGRPCHandler creates a new AccountGRPCHandler.
func NewAccountGRPCHandler(svc *service.AccountService) *AccountGRPCHandler {
	return &AccountGRPCHandler{svc: svc}
}

// CreateAccount creates a new account via gRPC.
func (h *AccountGRPCHandler) CreateAccount(
	_ context.Context,
	req *pb.CreateAccountRequest,
) (*pb.CreateAccountResponse, error) {
	if req.GetName() == "" || req.GetEmail() == "" {
		return nil, grpcstatus.Error(codes.InvalidArgument, "name and email are required")
	}

	acc, err := h.svc.Create(service.CreateAccountInput{
		Name:  req.GetName(),
		Email: req.GetEmail(),
	})
	if err != nil {
		return nil, grpcstatus.Error(codes.Internal, "failed to create account")
	}

	return &pb.CreateAccountResponse{
		Account: &pb.Account{
			Id:        acc.ID,
			Name:      acc.Name,
			Email:     acc.Email,
			CreatedAt: acc.CreatedAt.String(),
		},
	}, nil
}

// GetAccount retrieves an account by ID via gRPC.
func (h *AccountGRPCHandler) GetAccount(
	_ context.Context,
	req *pb.GetAccountRequest,
) (*pb.GetAccountResponse, error) {
	if req.GetId() == "" {
		return nil, grpcstatus.Error(codes.InvalidArgument, "id is required")
	}

	acc, err := h.svc.GetByID(req.GetId())
	if err != nil {
		if errors.Is(err, store.ErrNotFound) {
			return nil, grpcstatus.Error(codes.NotFound, "account not found")
		}
		return nil, grpcstatus.Error(codes.Internal, "failed to get account")
	}

	return &pb.GetAccountResponse{
		Account: &pb.Account{
			Id:        acc.ID,
			Name:      acc.Name,
			Email:     acc.Email,
			CreatedAt: acc.CreatedAt.String(),
		},
	}, nil
}

// ListAccounts returns all accounts via gRPC.
func (h *AccountGRPCHandler) ListAccounts(
	_ context.Context,
	_ *pb.ListAccountsRequest,
) (*pb.ListAccountsResponse, error) {
	accounts, err := h.svc.List()
	if err != nil {
		return nil, grpcstatus.Error(codes.Internal, "failed to list accounts")
	}

	pbAccounts := make([]*pb.Account, 0, len(accounts))
	for _, acc := range accounts {
		pbAccounts = append(pbAccounts, &pb.Account{
			Id:        acc.ID,
			Name:      acc.Name,
			Email:     acc.Email,
			CreatedAt: acc.CreatedAt.String(),
		})
	}

	return &pb.ListAccountsResponse{Accounts: pbAccounts}, nil
}
