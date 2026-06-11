import childProcess from "node:child_process";
import { EventEmitter } from "node:events";
import { syncBuiltinESMExports } from "node:module";

const originalExec = childProcess.exec;

childProcess.exec = function exec(command, options, callback) {
  const normalizedCommand = Array.isArray(command) ? command.join(" ") : command;

  if (typeof normalizedCommand === "string" && normalizedCommand.trim() === "net use") {
    const cb = typeof options === "function" ? options : callback;
    queueMicrotask(() => cb?.(null, "", ""));

    const child = new EventEmitter();
    child.stdout = new EventEmitter();
    child.stderr = new EventEmitter();
    child.stdin = null;
    child.kill = () => false;
    return child;
  }

  return originalExec.apply(this, arguments);
};

syncBuiltinESMExports();
