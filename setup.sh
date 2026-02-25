#!/bin/bash
set -e

die() {
    echo "PlantPi setup failed: $1"
    exit 1
}

## Pyenv Deps and tools
echo "Running initial PlantPi setup, you will be asked for a sudo password to install a few packages"

echo "Apt updating and upgrading..."
sudo apt update  || die "Failed to update"
sudo apt -y upgrade  || die "Failed to update"

echo "Apt installing [vim, ssh, curl, git, realvnc-vnc-server, pyenv build deps]..."
sudo apt install -y vim ssh curl git realvnc-vnc-server \
    make build-essential libssl-dev zlib1g-dev libbz2-dev libreadline-dev \
    libsqlite3-dev llvm libncursesw5-dev xz-utils tk-dev libxml2-dev \
    libxmlsec1-dev libffi-dev liblzma-dev || die "Failed to install system packages"

## Pyenv Install
if [[ ! -d "$HOME/.pyenv" ]]; then
    echo "Installing pyenv..."
    curl https://pyenv.run | bash || die "Failed to install pyenv"

    export PYENV_ROOT="$HOME/.pyenv"
    export PATH="$PYENV_ROOT/bin:$PATH"
    eval "$(pyenv init -)"

    cat >> ~/.bashrc << 'BASHRC'
    export PYENV_ROOT="$HOME/.pyenv"
    [[ -d $PYENV_ROOT/bin ]] && export PATH="$PYENV_ROOT/bin:$PATH"
    eval "$(pyenv init -)"
BASHRC
fi

export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init -)"

## Python Install
PYTHON_VER=$(pyenv install --list | grep 3.12 | head -1 | xargs)
echo "Installing Python $PYTHON_VER via pyenv (this may take several minutes on a Pi)..."
pyenv install "$PYTHON_VER" || die "Failed to install Python $PYTHON_VER via pyenv"
pyenv global "$PYTHON_VER"

## PlantPi Deps
echo "Pip installing PlantPi dependencies..."
pip install gpiozero matplotlib Adafruit_ADS1x15 flask sshkeyboard werkzeug || die "Failed to install Python packages"

## Allow I2C, SPI & VNC
sudo raspi-config nonint do_i2c 1
sudo raspi-config nonint do_spi 1
sudo raspi-config nonint do_vnc 1

## Service File
echo "Writing systemd service file..."
SERVICE_USER=$(whoami)
SERVICE_HOME=$(eval echo "~$SERVICE_USER")
cat > /tmp/plantpi.service << SVCEOF
[Unit]
Description=PlantPi Plant Watering System
After=network.target

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$SERVICE_HOME/git/PlantPi
Environment="PYENV_ROOT=$SERVICE_HOME/.pyenv"
Environment="PATH=$SERVICE_HOME/.pyenv/shims:$SERVICE_HOME/.pyenv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ExecStart=$SERVICE_HOME/.pyenv/shims/python3 -u $SERVICE_HOME/git/PlantPi/PlantPi.py -c $SERVICE_HOME/git/PlantPi/plantpi.json
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SVCEOF

## Service Load
sudo mv /tmp/plantpi.service /etc/systemd/system/plantpi.service
sudo systemctl daemon-reload
sudo systemctl enable plantpi

echo "Your PlantPi is now configured and should be able to run PlantPi.py"
