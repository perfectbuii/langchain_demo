package middleware

import (
	"bytes"
	"encoding/json"
	"io"
	"log"
	"net/http"
	"time"
)

// responseRecorder wraps http.ResponseWriter to capture status code and body.
type responseRecorder struct {
	http.ResponseWriter
	status int
	body   bytes.Buffer
}

func (r *responseRecorder) WriteHeader(status int) {
	r.status = status
	r.ResponseWriter.WriteHeader(status)
}

func (r *responseRecorder) Write(b []byte) (int, error) {
	r.body.Write(b)
	return r.ResponseWriter.Write(b)
}

// Logging is an HTTP middleware that prints request and response details.
func Logging(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()

		// Read and restore request body.
		var reqBody string
		if r.Body != nil && r.Body != http.NoBody {
			raw, err := io.ReadAll(r.Body)
			if err == nil {
				r.Body = io.NopCloser(bytes.NewReader(raw))
				reqBody = compactJSON(raw)
			}
		}

		rec := &responseRecorder{ResponseWriter: w, status: http.StatusOK}
		next.ServeHTTP(rec, r)

		elapsed := time.Since(start)
		respBody := compactJSON(rec.body.Bytes())

		log.Printf("[HTTP] %s %s | req: %s \u2192 %d | resp: %s | %s",
			r.Method, r.URL.Path,
			reqBody,
			rec.status,
			respBody,
			elapsed,
		)
	})
}

// compactJSON returns a compact single-line JSON string, or the raw text if
// it is not valid JSON (e.g. plain-text error messages).
func compactJSON(b []byte) string {
	trimmed := bytes.TrimSpace(b)
	if len(trimmed) == 0 {
		return "<empty>"
	}
	var buf bytes.Buffer
	if err := json.Compact(&buf, trimmed); err == nil {
		return buf.String()
	}
	return string(trimmed)
}
