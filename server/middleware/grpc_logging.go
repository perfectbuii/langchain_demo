package middleware

import (
	"context"
	"encoding/json"
	"log"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/status"
)

// GRPCLogging returns a gRPC unary server interceptor that logs every RPC's
// request payload, response payload, status code, and elapsed time.
func GRPCLogging() grpc.UnaryServerInterceptor {
	return func(
		ctx context.Context,
		req any,
		info *grpc.UnaryServerInfo,
		handler grpc.UnaryHandler,
	) (any, error) {
		start := time.Now()

		resp, err := handler(ctx, req)

		elapsed := time.Since(start)
		code := status.Code(err)

		log.Printf("[gRPC] %s | req: %s → %s | resp: %s | %s",
			info.FullMethod,
			marshalProto(req),
			code,
			marshalProto(resp),
			elapsed,
		)

		return resp, err
	}
}

// marshalProto serialises v to compact JSON.  Falls back to a placeholder on error.
func marshalProto(v any) string {
	if v == nil {
		return "<nil>"
	}
	b, err := json.Marshal(v)
	if err != nil {
		return "<unmarshalable>"
	}
	return string(b)
}
