(docker-install)=
# `docker` based setup

Within the FABulous repo we provide a Dockerfile that allows users to run the FABulous flow within a Docker container, installing all requirements automatically.

## Setting up the Docker environment

To set up the Docker environment, navigate to the FABulous root directory and run:

```bash
docker build -t fabulous .
```

## Running the Docker environment

To run the Docker environment, stay in the FABulous root directory (this is vital as the command mounts the current directory as the container's filesystem) and run:

```bash
docker run -it -v $PWD:/workspace fabulous
```

This will bring up an interactive bash environment within the Docker container, within which you can use FABulous as if hosted natively on your machine. When you are finished using FABulous, simply type `exit`, and all changes made will have been made to your copy of the FABulous repository.
