FROM ubuntu:latest

WORKDIR /home
RUN apt update && apt-get install

# install python3.12
RUN apt install -y python3 python3-pip python3-venv python3-tk

# setup virtaul environment
ENV VIRTUAL_ENV="/venv"
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
ENV FAB_ROOT=/home
RUN python3 -m venv $VIRTUAL_ENV

# install requirements
COPY . .
RUN python3 -m pip install pip --upgrade
RUN pip3 install -r requirements.txt

# install yosys
RUN apt install -y yosys

#install nextpnr
RUN apt install -y nextpnr-generic

#install ghdl
RUN apt install -y ghdl

# install GTKwave
RUN apt install -y gtkwave

# install icarus
RUN apt install -y iverilog