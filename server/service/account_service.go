package service

import (
	"time"

	"github.com/google/uuid"
	"github.com/perfectbuii/account-server/model"
	"github.com/perfectbuii/account-server/store"
)

// AccountService contains the business logic for the accounts domain.
type AccountService struct {
	store *store.AccountStore
}

// NewAccountService creates a new AccountService.
func NewAccountService(store *store.AccountStore) *AccountService {
	return &AccountService{store: store}
}

// CreateAccountInput holds the data required to create an account.
type CreateAccountInput struct {
	Name  string
	Email string
}

// Create creates a new account.
func (s *AccountService) Create(input CreateAccountInput) (*model.Account, error) {
	acc := &model.Account{
		ID:        uuid.New().String(),
		Name:      input.Name,
		Email:     input.Email,
		CreatedAt: time.Now().UTC(),
	}
	return s.store.Create(acc)
}

// GetByID returns an account by its ID.
func (s *AccountService) GetByID(id string) (*model.Account, error) {
	return s.store.GetByID(id)
}

// List returns all accounts.
func (s *AccountService) List() ([]*model.Account, error) {
	return s.store.List()
}
