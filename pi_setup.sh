#!/bin/bash

# TODO:
#	-Test pass and local
#	-
#	-
#	-	
#	-

usage()
{
	echo "pi_setup.sh [OPTS]"
	echo
	echo "Options:"
	echo "-----------------------------------"
	echo "-i/--rpi-ip arg (ex: 127.0.0.1): The IPv4 address or hostname of the target Pi"
	echo "-u/--pi-user arg (ex: johnsmith): Required unless -l/--local-setup is specified. The user account to use when connecting to the Pi"
	echo "-p/--pi-pass arg (ex: password): The password for the specified user. NOTE: This will not work unless you have 'sshpass' installed"
	echo "-d/--dev-env: Setting this option adds a few more steps to setup.sh to add some handy dev packages"
	echo "-l/--local-setup: Set this option if running this script directly on the Pi, otherwise the script will attempt a remote connection"
	echo "-b/--bashrc: arg (ex: ~/.bashrc): Onlt works when --dev-env is set. A path to a bash script to get pasted in at the bottom of the pi's bashrc"
	echo "-h/--help: Dislpay this message"
	exit 0
}

die()
{
	echo "PlantPi setup failed: "$1
	rm $PLANTPI_PATH/setup.sh
	rm $PLANTPI_PATH/bashrc
	exit 1
}

PI_IP=plantpi.local
LOCAL=false
DEV=false
PLANTPI_PATH=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
SSH=ssh
while [[ $# -gt 0 ]];
do
	case $1 in
		-i|--rpi-ip )		PI_IP="$2" && shift && shift ;;
		-u|--pi-user )		USER="$2" && shift && shift ;;
		-p|--pi-pass )		PASS="$2" && shift && shift ;;
		-d|--dev-env )		DEV=true && shift ;;
		-l|--local-setup )	LOCAL=true && shift ;;
		-b|--bashrc ) 		USER_RC="$2" && shift && shift ;;
		-h|--help )			usage
	esac
done

if [[ $LOCAL == false ]]; then
	if [[ -z $USER ]]; then
		die "User must be specified when performing a remote setup"
	elif [[ -n $PASS && -z $(which sshpass) ]]; then
		die "sshpass either not installed or not in path. Try again, either after installing it or don't use the --pi-pass option"
	elif [[ -n $PASS && -n $(which sshpass) ]]; then
		SSH="sshpass -f <(printf '%s\\n' "$PASS") ssh"
	fi

	PO=$(ping -o -t 1 $PI_IP 2>/dev/null)
	if [[ -z $PO || $PO == *timeout* ]]; then
		die "Cannot ping "$PI_IP", please double check the address"
	fi
else
	PLANTPI_PATH=~
fi

# Pi
cat << EOF > $PLANTPI_PATH/setup.sh
#!/bin/bash
set -x
die()
{
    echo "PlantPi setup failed: "\$1
    exit 1
}
echo "Running initial PlantPi setup, you will be asked for a sudo password to install a few packages"
echo "Apt updating and upgrading..."
sudo apt update && \
sudo apt -y upgrade && \ 
echo "Apt installing [vim, python3, ssh, realvnc-vnc-server]..." && \
sudo apt install -y vim python3 ssh realvnc-vnc-server && \
echo "Pip installing [gpiozero, matplotlib, Adafruit_ADS1x15]..." && \
pip3 install gpiozero matplotlib Adafruit_ADS1x15 || die "Failed to install needed packages"
if [[ -f ~/bashrc ]]; then
    cat ~/bashrc >> ~/.bashrc
    rm ~/bashrc
fi
mkdir -p ~/git || die "Failed to make '~/git' directory"
pushd git
git clone git@github.com:ZenixineZ/PlantPi.git || die "Failed to clone PlantPi from github"
popd
set +x

EOF

if [[ $DEV == true ]];then
cat << EOF >> $PLANTPI_PATH/setup.sh
wget -qO - https://download.sublimetext.com/sublimehq-pub.gpg | gpg --dearmor | sudo tee /etc/apt/trusted.gpg.d/sublimehq-archive.gpg > /dev/null
echo "deb https://download.sublimetext.com/ apt/stable/" | sudo tee /etc/apt/sources.list.d/sublime-text.list
sudo apt update
sudo apt install -y sublime-text spyder

EOF

chmod +x $PLANTPI_PATH/setup.sh
BASHRC=$(cat << EOF
alias ls='ls --color=auto'
alias gti='git'
alias la="ls -AFG"
alias sbrc="source ~/.bashrc"
alias ll='ls -alFG'
alias ls='ls -G'
alias lt='ls -latr'
alias clonepp='git clone git@github.com:ZenixineZ/PlantPi.git'

source /usr/share/bash-completion/completions/git
PS1='\${debian_chroot:+(\$debian_chroot)}\\[\\033[01;32m\\]\\u@\\h\\[\\033[00m\\]:\\[\\033[01;34m\\]\\w\[\\033[00m\\]'
export PS1="\$PS1\$(__git_ps1)\\[\\033[00m\\]\$ "

EOF
)
fi

# Host
if [[ $LOCAL == false ]]; then
	if [[ ! -d ~/.ssh || ! -f ~/.ssh/id_rsa.pub ]]; then
		echo "You don't yet have an RSA SSH key. Would you like to generate one? (y/n)"
		read cont
		if [[ $cont == 'y' ]];then
			ssh-keygen -t id_rsa	
		fi
	fi

	KEY=$(cat ~/.ssh/id_rsa.pub)
	CMD=$SSH' '$USER@$PI_IP' "mkdir -p ~/.ssh && echo $KEY >> ~/.ssh/authorized_keys"'
	echo "Copying your SSH key to the pi and adding it to authorized_keys for easy login..."
	eval $CMD || die "Failed to add your ssh key to the pi's '~/.ssh/authorized_keys' file"
	echo "Copying the setup script to the pi..."
	scp $PLANTPI_PATH/setup.sh $USER@$PI_IP:/home/$USER/setup.sh || die "Failed to scp 'setup.sh' to pi"
	if [[ $DEV == true ]];then
		echo -n "Copying some handy aliases and such to the pi's .bashrc"
		if [[ -f $USER_RC ]]; then
			echo ', as well as the contents of '$USER_RC'...'
			UBRC_TEXT=$(cat $USER_RC)
			SUB_CMD=' && echo '$UBRC_TEXT' >> ~/.bashrc' 
		else
			echo ...
		fi
		CMD=$SSH' '$USER'@'$PI_IP' "echo $BASHRC >> ~/.bashrc'$SUB_CMD'"' 
		eval $CMD || die "Failed to scp bashrc to pi"
	fi
	echo "Running setup.sh..."
	CMD=$SSH' '$USER'@'$PI_IP' "~/setup.sh"'
	eval $CMD || die "Failed to run setup.sh on pi"

	rm $PLANTPI_PATH/setup.sh
else
	if [[ ! -d ~/.ssh || ! -f ~/.ssh/id_rsa.pub ]]; then
		echo "You don't yet have an RSA SSH key. Would you like to generate one? (y/n)"
		read cont
		if [[ $cont == 'y' ]];then
			ssh-keygen -t id_rsa	
		fi
	fi
	echo "Running setup.sh..."
	~/setup.sh
fi
rm $PLANTPI_PATH/bashrc

echo "Your PlantPi is now configured and should be able to run PlantPi.py"
