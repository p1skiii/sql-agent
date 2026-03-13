import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

function isRelativeSpecifier(specifier) {
  return specifier.startsWith("./") || specifier.startsWith("../");
}

export async function resolve(specifier, context, nextResolve) {
  if (specifier === "next/server") {
    return nextResolve("next/server.js", context);
  }

  if (isRelativeSpecifier(specifier) && !path.extname(specifier) && context.parentURL) {
    const parentPath = fileURLToPath(context.parentURL);
    const candidate = path.resolve(path.dirname(parentPath), `${specifier}.ts`);
    if (fs.existsSync(candidate)) {
      return nextResolve(pathToFileURL(candidate).href, context);
    }
  }

  return nextResolve(specifier, context);
}
