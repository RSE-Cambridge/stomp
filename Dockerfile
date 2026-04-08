FROM ubuntu:22.04
ARG UID
ARG GID
RUN echo "Group ID: $GID"
RUN echo "User ID: $UID"

USER root
RUN apt-get update -y && apt-get install apt-utils -y
RUN DEBIAN_FRONTEND="noninteractive" apt-get -y install tzdata

# Install basic packages 
RUN apt-get upgrade -y 
RUN apt-get update -y \
    && apt-get install -y verilator gcc-riscv64-unknown-elf \
                          libgmp-dev python3 python3-pip g++\
                          clang llvm lld clang-tidy clang-format \
                          gcc-multilib gcc cmake sudo wget vim \
                          curl tmux git bc boolector
RUN apt-get install -y gfortran
RUN apt-get install -y autoconf gperf

CMD ["bash"]

# Add dev-user
RUN groupadd -o -g $GID dev-user
RUN useradd -r -g $GID -u $UID -m -d /home/dev-user -s /sbin/nologin -c "User" dev-user
RUN echo "dev-user     ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers
USER dev-user

# Install Python packages 
ENV PATH="${PATH}:/home/dev-user/.local/bin"
RUN pip3 install --user --upgrade pip \
    && pip3 install black colorlog toml tabulate isort \
         pytest-xdist pytest-cov mpmath termcolor sympy \
         pyparsing MarkupSafe graphviz configparser Jinja2 \
         sphinx-autoapi autoapi sphinx-autodoc-typehints \
         sphinx-design sphinxcontrib-bibtex flake8 z3-solver

# Add environment variables
RUN printf "\
\nexport LIBRARY_PATH=/usr/lib/x86_64-linux-gnu:\$LIBRARY_PATH \
\n# Basic PATH setup \
\nexport PATH=/workspace/scripts:/home/dev-user/.local/bin:\$PATH \
\n# Thread setup \
\nexport nproc=\$(grep -c ^processor /proc/cpuinfo) \
\nexport PYTHONDONTWRITEBYTECODE=1 \
\n(cd /workspace/PSyclone/external/fparser && pip install --user .) \
\n(cd /workspace/PSyclone/ && pip install --user -e .) \
\n# Terminal color... \
\nexport LC_ALL=C.utf8 \
\nexport PS1=$'\u25b6 ' \
\nexport LS_COLORS='rs=0:di=01;96:ln=01;36:mh=00:pi=40;33:so=01;35:do=01;35:bd=40;33;01' \
\nalias ls='ls --color' \
\nalias grep='grep --color'\n" >> /home/dev-user/.bashrc

RUN printf "\
\nset nowrapscan \
\nnmap <C-Up> k?^\! ===<CR>kzt \
\nnmap <C-Down> jj/^\! ===<CR>kzt \
\nxmap <Space> :w !cat > /tmp/file.F90 && clear && echo Running existing analysis... && psyclone -s parallelise.py -o /dev/null /tmp/file.F90 && echo && echo Running new analysis... && export USE_SMT=yes && psyclone -s parallelise.py -o /dev/null /tmp/file.F90<CR>\n" >> /home/dev-user/.vimrc

# Entrypoint set up
WORKDIR workspace
