#!/bin/bash

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print error messages
error() {
    echo -e "${RED}Error: $1${NC}" >&2
    exit 1
}

# Function to print success messages
success() {
    echo -e "${GREEN}$1${NC}"
}

# Function to print info messages
info() {
    echo -e "${YELLOW}$1${NC}"
}

# Check if Xcode Command Line Tools are installed
check_xcode() {
    info "Checking Xcode Command Line Tools..."
    if ! command -v xcodebuild >/dev/null 2>&1; then
        error "Xcode Command Line Tools not found. Please install them using: xcode-select --install"
    fi
    success "Xcode Command Line Tools found"
}

# Check Swift version
check_swift_version() {
    info "Checking Swift version..."
    local swift_version=$(swift --version | grep -o "Swift version [0-9.]*" | cut -d' ' -f3)
    if [ -z "$swift_version" ]; then
        error "Could not determine Swift version"
    fi
    
    # Compare versions (requires Swift 6.0 or higher)
    if [ "$(printf '%s\n' "6.0" "$swift_version" | sort -V | head -n1)" != "6.0" ]; then
        error "Swift version 6.0 or higher is required (found $swift_version)"
    fi
    success "Swift version $swift_version found"
}

# Build the package
build_package() {
    info "Building SwiftAgent..."
    if ! swift build -c release; then
        error "Failed to build SwiftAgent"
    fi
    success "Successfully built SwiftAgent"
}

# Install the package
install_package() {
    info "Installing SwiftAgent..."
    
    # Create installation directories if they don't exist
    local install_dir="/usr/local/lib/SwiftAgent"
    local bin_dir="/usr/local/bin"
    
    sudo mkdir -p "$install_dir" || error "Failed to create installation directory"
    
    # Copy built products
    local build_dir=".build/release"
    
    if [ -d "$build_dir" ]; then
        sudo cp -R "$build_dir/"* "$install_dir/" || error "Failed to copy build products"
        
        # Create symbolic links for executables
        if [ -f "$install_dir/AgentCLI" ]; then
            sudo ln -sf "$install_dir/AgentCLI" "$bin_dir/agent"
        fi
        
        success "Successfully installed SwiftAgent"
    else
        error "Build directory not found"
    fi
}

# Main installation process
main() {
    echo "SwiftAgent Installation Script"
    echo "-------------------------"
    
    # Perform checks
    check_xcode
    check_swift_version
    
    # Build and install
    build_package
    install_package
    
    echo
    success "SwiftAgent has been successfully installed!"
    echo "You can now use 'agent' from the command line"
}

# Run main installation process
main
