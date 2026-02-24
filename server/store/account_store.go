package store

import (
	"errors"
	"sync"

	"github.com/perfectbuii/account-server/model"
)

// ErrNotFound is returned when an account is not found.
var ErrNotFound = errors.New("account not found")

// AccountStore is an in-memory store for accounts.
type AccountStore struct {
	mu       sync.RWMutex
	accounts map[string]*model.Account
}

// NewAccountStore creates a new AccountStore.
func NewAccountStore() *AccountStore {
	return &AccountStore{
		accounts: make(map[string]*model.Account),
	}
}

// Create saves a new account and returns it.
func (s *AccountStore) Create(acc *model.Account) (*model.Account, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	s.accounts[acc.ID] = acc
	return acc, nil
}

// GetByID returns an account by its ID.
func (s *AccountStore) GetByID(id string) (*model.Account, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	acc, ok := s.accounts[id]
	if !ok {
		return nil, ErrNotFound
	}
	return acc, nil
}

// List returns all accounts.
func (s *AccountStore) List() ([]*model.Account, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	accounts := make([]*model.Account, 0, len(s.accounts))
	for _, acc := range s.accounts {
		accounts = append(accounts, acc)
	}
	return accounts, nil
}
