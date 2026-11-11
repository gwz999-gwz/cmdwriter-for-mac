#import <AppKit/AppKit.h>

@interface CapsWriterDelegate : NSObject <NSApplicationDelegate>
@property NSMutableArray<NSString *> *pendingFiles;
@property NSTask *child;
@property BOOL launchScheduled;
@end

@implementation CapsWriterDelegate

- (instancetype)init {
    if ((self = [super init])) {
        _pendingFiles = [NSMutableArray array];
    }
    return self;
}

- (void)application:(NSApplication *)sender openFiles:(NSArray<NSString *> *)filenames {
    [self.pendingFiles addObjectsFromArray:filenames];
    [self scheduleLaunch];
    [sender replyToOpenOrPrint:NSApplicationDelegateReplySuccess];
}

- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    [self scheduleLaunch];
}

- (void)scheduleLaunch {
    if (self.launchScheduled) return;
    self.launchScheduled = YES;
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 350 * NSEC_PER_MSEC),
                   dispatch_get_main_queue(), ^{ [self launchCapsWriter]; });
}

- (void)showError:(NSString *)title message:(NSString *)message {
    NSAlert *alert = [[NSAlert alloc] init];
    alert.messageText = title;
    alert.informativeText = message;
    alert.alertStyle = NSAlertStyleCritical;
    [alert runModal];
}

- (void)launchCapsWriter {
    if (self.child) return;

    NSURL *executable = [NSURL fileURLWithPath:NSProcessInfo.processInfo.arguments[0]];
    NSURL *projectDir = [[[[[executable URLByDeletingLastPathComponent]
                            URLByDeletingLastPathComponent]
                           URLByDeletingLastPathComponent]
                          URLByDeletingLastPathComponent] URLByStandardizingPath];
    NSURL *python = [projectDir URLByAppendingPathComponent:@".venv/bin/python"];
    NSURL *startScript = [projectDir URLByAppendingPathComponent:@"start.py"];
    NSURL *logDir = [projectDir URLByAppendingPathComponent:@"logs"];
    NSURL *logFile = [logDir URLByAppendingPathComponent:@"app-launch.log"];

    if (![[NSFileManager defaultManager] isExecutableFileAtPath:python.path]) {
        [self showError:@"无法启动 / Cannot start CmdWriter"
                message:@"未找到项目虚拟环境 .venv。请先按照 README.md 安装依赖。\nThe .venv directory is missing. Follow README.md to install the dependencies."];
        [NSApp terminate:nil];
        return;
    }

    [[NSFileManager defaultManager] createDirectoryAtURL:logDir
                              withIntermediateDirectories:YES attributes:nil error:nil];
    if (![[NSFileManager defaultManager] fileExistsAtPath:logFile.path]) {
        [[NSFileManager defaultManager] createFileAtPath:logFile.path contents:nil attributes:nil];
    }
    NSFileHandle *logHandle = [NSFileHandle fileHandleForWritingAtPath:logFile.path];
    [logHandle seekToEndOfFile];

    NSTask *task = [[NSTask alloc] init];
    task.executableURL = python;
    task.arguments = [@[startScript.path] arrayByAddingObjectsFromArray:self.pendingFiles];
    task.currentDirectoryURL = projectDir;
    task.standardOutput = logHandle;
    task.standardError = logHandle;
    task.terminationHandler = ^(NSTask *finished) {
        dispatch_async(dispatch_get_main_queue(), ^{ [NSApp terminate:nil]; });
    };

    NSError *error = nil;
    if (![task launchAndReturnError:&error]) {
        [self showError:@"启动失败 / CmdWriter startup failed" message:error.localizedDescription];
        [NSApp terminate:nil];
        return;
    }
    self.child = task;
}

- (void)applicationWillTerminate:(NSNotification *)notification {
    if (self.child.running) [self.child terminate];
}

@end

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        NSApplication *app = [NSApplication sharedApplication];
        CapsWriterDelegate *delegate = [[CapsWriterDelegate alloc] init];
        app.delegate = delegate;
        [app setActivationPolicy:NSApplicationActivationPolicyAccessory];
        [app run];
    }
    return 0;
}
