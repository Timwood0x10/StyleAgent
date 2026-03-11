#!/bin/bash
#
# Docker Service Management Script
#
# This script provides simple commands to start/stop Docker services required by iFlow.
# Services: PostgreSQL with pgvector, Ollama (LLM)
#
# Usage:
#   ./docker.sh start     - Start all services
#   ./docker.sh stop      - Stop all services
#   ./docker.sh status    - Check service status
#   ./docker.sh restart   - Restart all services
#

set -e

# Configuration
POSTGRES_CONTAINER_NAME="iflow-postgres"
POSTGRES_PORT="${PG_PORT:-5433}"
POSTGRES_DB="${PG_DATABASE:-iflow}"
POSTGRES_USER="${PG_USER:-postgres}"
POSTGRES_PASSWORD="${PG_PASSWORD:-postgres}"

OLLAMA_CONTAINER_NAME="iflow-ollama"
OLLAMA_PORT="${OLLAMA_PORT:-11434}"
OLLAMA_MODEL="${LLM_MODEL:-gpt-oss:20b}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if Docker is running
check_docker() {
    if ! docker info > /dev/null 2>&1; then
        log_error "Docker is not running. Please start Docker first."
        exit 1
    fi
}

# Start PostgreSQL with pgvector
start_postgres() {
    log_info "Starting PostgreSQL with pgvector..."

    if docker ps -a --format '{{.Names}}' | grep -q "^${POSTGRES_CONTAINER_NAME}$"; then
        if docker ps --format '{{.Names}}' | grep -q "^${POSTGRES_CONTAINER_NAME}$"; then
            log_warn "PostgreSQL container is already running"
        else
            log_info "Starting existing PostgreSQL container..."
            docker start "$POSTGRES_CONTAINER_NAME"
        fi
    else
        log_info "Creating new PostgreSQL container..."
        docker run -d \
            --name "$POSTGRES_CONTAINER_NAME" \
            -e POSTGRES_USER="$POSTGRES_USER" \
            -e POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
            -e POSTGRES_DB="$POSTGRES_DB" \
            -p "${POSTGRES_PORT}:5432" \
            pgvector/pgvector:pg16
        log_info "PostgreSQL started on port ${POSTGRES_PORT}"
    fi
}

# Start Ollama
start_ollama() {
    log_info "Starting Ollama..."

    if docker ps -a --format '{{.Names}}' | grep -q "^${OLLAMA_CONTAINER_NAME}$"; then
        if docker ps --format '{{.Names}}' | grep -q "^${OLLAMA_CONTAINER_NAME}$"; then
            log_warn "Ollama container is already running"
        else
            log_info "Starting existing Ollama container..."
            docker start "$OLLAMA_CONTAINER_NAME"
        fi
    else
        log_info "Creating new Ollama container..."
        docker run -d \
            --name "$OLLAMA_CONTAINER_NAME" \
            -p "${OLLAMA_PORT}:11434" \
            -v ollama_data:/root/.ollama \
            ollama/ollama:latest
        log_info "Ollama started on port ${OLLAMA_PORT}"
        log_info "Note: You may need to pull the model: docker exec ${OLLAMA_CONTAINER_NAME} ollama pull ${OLLAMA_MODEL}"
    fi
}

# Stop all services
stop_services() {
    log_info "Stopping services..."

    if docker ps --format '{{.Names}}' | grep -q "^${POSTGRES_CONTAINER_NAME}$"; then
        docker stop "$POSTGRES_CONTAINER_NAME" > /dev/null 2>&1 || true
        log_info "PostgreSQL stopped"
    fi

    if docker ps --format '{{.Names}}' | grep -q "^${OLLAMA_CONTAINER_NAME}$"; then
        docker stop "$OLLAMA_CONTAINER_NAME" > /dev/null 2>&1 || true
        log_info "Ollama stopped"
    fi
}

# Show service status
show_status() {
    echo "=========================================="
    echo "         Service Status"
    echo "=========================================="

    # PostgreSQL
    if docker ps --format '{{.Names}}' | grep -q "^${POSTGRES_CONTAINER_NAME}$"; then
        echo -e "PostgreSQL:    ${GREEN}Running${NC} (port ${POSTGRES_PORT})"
    else
        echo -e "PostgreSQL:    ${RED}Stopped${NC}"
    fi

    # Ollama
    if docker ps --format '{{.Names}}' | grep -q "^${OLLAMA_CONTAINER_NAME}$"; then
        echo -e "Ollama:        ${GREEN}Running${NC} (port ${OLLAMA_PORT})"
    else
        echo -e "Ollama:        ${RED}Stopped${NC}"
    fi

    echo "=========================================="
}

# Main entry point
main() {
    check_docker

    case "${1:-}" in
        start)
            start_postgres
            start_ollama
            log_info "All services started successfully!"
            show_status
            ;;
        stop)
            stop_services
            log_info "All services stopped!"
            ;;
        status)
            show_status
            ;;
        restart)
            stop_services
            sleep 2
            start_postgres
            start_ollama
            log_info "All services restarted!"
            show_status
            ;;
        *)
            echo "Usage: $0 {start|stop|status|restart}"
            echo ""
            echo "Commands:"
            echo "  start   - Start all Docker services (PostgreSQL + Ollama)"
            echo "  stop    - Stop all Docker services"
            echo "  status  - Show status of all services"
            echo "  restart - Restart all Docker services"
            exit 1
            ;;
    esac
}

main "$@"
