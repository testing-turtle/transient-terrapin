import { exec as cp_exec } from 'child_process';

export function exec(command: string, options?: { env?: NodeJS.ProcessEnv | undefined; }) {
  return new Promise<{ stdout: string, stderr: string }>((resolve, reject) => {
    cp_exec(command, (error, stdout, stderr) => {
      if (error) {
        reject(error);
      } else {
        resolve({ stdout, stderr });
      }
    });
  });
}

export function getRequiredEnvVariable(name: string): string {
  const value = process.env[name];
  if (!value) {
    console.log(`Environment variable ${name} is not set`);
    process.exit(1);
  }
  return value;
}
