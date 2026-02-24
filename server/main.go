package main

import (
	"context"
	"fmt"
	"log"
	"net"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/perfectbuii/account-server/handler"
	"github.com/perfectbuii/account-server/middleware"
	pb "github.com/perfectbuii/account-server/proto/account"
	"github.com/perfectbuii/account-server/service"
	"github.com/perfectbuii/account-server/store"
	"google.golang.org/grpc"
	"google.golang.org/grpc/reflection"
)

const (
	httpAddr = ":8080"
	grpcAddr = ":9090"
)

func main() {
	// ── shared dependencies ───────────────────────────────────────────────────
	accountStore := store.NewAccountStore()
	accountSvc := service.NewAccountService(accountStore)

	// ── HTTP server ───────────────────────────────────────────────────────────
	mux := http.NewServeMux()
	httpHandler := handler.NewAccountHTTPHandler(accountSvc)
	httpHandler.RegisterRoutes(mux)

	httpServer := &http.Server{
		Addr:         httpAddr,
		Handler:      middleware.Logging(mux),
		ReadTimeout:  10 * time.Second,
		WriteTimeout: 10 * time.Second,
	}

	// ── gRPC server ───────────────────────────────────────────────────────────
	grpcServer := grpc.NewServer(
		grpc.UnaryInterceptor(middleware.GRPCLogging()),
	)
	grpcHandler := handler.NewAccountGRPCHandler(accountSvc)
	pb.RegisterAccountServiceServer(grpcServer, grpcHandler)
	reflection.Register(grpcServer) // enables grpcurl / postman introspection

	// ── start servers ─────────────────────────────────────────────────────────
	go func() {
		fmt.Printf("HTTP server listening on %s\n", httpAddr)
		if err := httpServer.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("HTTP server error: %v", err)
		}
	}()

	go func() {
		lis, err := net.Listen("tcp", grpcAddr)
		if err != nil {
			log.Fatalf("failed to listen for gRPC: %v", err)
		}
		fmt.Printf("gRPC server listening on %s\n", grpcAddr)
		if err := grpcServer.Serve(lis); err != nil {
			log.Fatalf("gRPC server error: %v", err)
		}
	}()

	// ── graceful shutdown ─────────────────────────────────────────────────────
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit

	log.Println("shutting down servers...")

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	if err := httpServer.Shutdown(ctx); err != nil {
		log.Printf("HTTP server shutdown error: %v", err)
	}

	grpcServer.GracefulStop()
	log.Println("servers stopped")
}
