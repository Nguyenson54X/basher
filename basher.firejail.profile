quiet
include /etc/firejail/disable-common.inc
include /etc/firejail/disable-programs.inc

private .
read-only ${HOME}/.git
protocol unix,inet,inet6
caps.drop all
seccomp
noroot
nonewprivs
private-dev
restrict-namespaces