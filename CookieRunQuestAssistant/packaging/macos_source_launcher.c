/* Native macOS entry point for the source-backed development app. */
#include <mach-o/dyld.h>
#include <limits.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
int main(void) {
    char path[PATH_MAX];
    uint32_t size = sizeof(path);
    if (_NSGetExecutablePath(path, &size) != 0) return 1;
    char *slash = strrchr(path, '/');
    if (!slash) return 1;
    *slash = '\0';
    if (strlen(path) + strlen("/launcher.command") >= sizeof(path)) return 1;
    strcat(path, "/launcher.command");
    execl("/bin/zsh", "zsh", path, (char *)NULL);
    perror("Unable to start quest assistant");
    return 1;
}
