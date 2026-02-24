package handler

import (
	"encoding/json"
	"errors"
	"net/http"
	"strings"

	"github.com/haobuihoan/account-server/service"
	"github.com/haobuihoan/account-server/store"
)

// AccountHTTPHandler handles HTTP requests for the accounts domain.
type AccountHTTPHandler struct {
	svc *service.AccountService
}

// NewAccountHTTPHandler creates a new AccountHTTPHandler.
func NewAccountHTTPHandler(svc *service.AccountService) *AccountHTTPHandler {
	return &AccountHTTPHandler{svc: svc}
}

// RegisterRoutes registers the HTTP routes on the given mux.
// Routes:
//
//	POST /accounts        → CreateAccount
//	GET  /accounts/{id}   → GetAccount
//	GET  /accounts        → ListAccounts
func (h *AccountHTTPHandler) RegisterRoutes(mux *http.ServeMux) {
	mux.HandleFunc("/accounts", h.handleAccounts)
	mux.HandleFunc("/accounts/", h.handleAccountByID)
}

// handleAccounts dispatches POST /accounts and GET /accounts.
func (h *AccountHTTPHandler) handleAccounts(w http.ResponseWriter, r *http.Request) {
	switch r.Method {
	case http.MethodPost:
		h.createAccount(w, r)
	case http.MethodGet:
		h.listAccounts(w, r)
	default:
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
	}
}

// handleAccountByID dispatches GET /accounts/{id}.
func (h *AccountHTTPHandler) handleAccountByID(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}

	// Extract {id} from the path "/accounts/{id}"
	id := strings.TrimPrefix(r.URL.Path, "/accounts/")
	if id == "" {
		http.Error(w, "missing account id", http.StatusBadRequest)
		return
	}
	h.getAccount(w, r, id)
}

// ── handlers ────────────────────────────────────────────────────────────────

func (h *AccountHTTPHandler) createAccount(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Name  string `json:"name"`
		Email string `json:"email"`
	}

	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "invalid request body", http.StatusBadRequest)
		return
	}

	if req.Name == "" || req.Email == "" {
		http.Error(w, "name and email are required", http.StatusBadRequest)
		return
	}

	acc, err := h.svc.Create(service.CreateAccountInput{
		Name:  req.Name,
		Email: req.Email,
	})
	if err != nil {
		http.Error(w, "failed to create account", http.StatusInternalServerError)
		return
	}

	writeJSON(w, http.StatusCreated, acc)
}

func (h *AccountHTTPHandler) getAccount(w http.ResponseWriter, _ *http.Request, id string) {
	acc, err := h.svc.GetByID(id)
	if err != nil {
		if errors.Is(err, store.ErrNotFound) {
			http.Error(w, "account not found", http.StatusNotFound)
			return
		}
		http.Error(w, "failed to get account", http.StatusInternalServerError)
		return
	}

	writeJSON(w, http.StatusOK, acc)
}

func (h *AccountHTTPHandler) listAccounts(w http.ResponseWriter, _ *http.Request) {
	accounts, err := h.svc.List()
	if err != nil {
		http.Error(w, "failed to list accounts", http.StatusInternalServerError)
		return
	}

	writeJSON(w, http.StatusOK, accounts)
}

// ── helpers ──────────────────────────────────────────────────────────────────

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}
