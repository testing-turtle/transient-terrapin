import fs from 'fs';
import crypto from 'crypto';
import yaml from 'yaml';

import { FileWithHash } from './repo.js';

/**
 * PathFilter class equivalent to the Python PathFilter
 */
class PathFilter {
  private _regex: RegExp | null;
  constructor(public expression: string) {
    this.expression = expression;
    this._regex = null;
  }

  /**
   * Get the regex object for this filter
   */
  get regex() {
    if (this._regex === null) {
      this._regex = new RegExp(this.expression);
    }
    return this._regex;
  }
}

/**
 * SkipIf class equivalent to the Python SkipIf
 */
class SkipIf {
  private _allFilesMatchAny: PathFilter[];
  constructor(allFilesMatchAny: string[]) {
    this._allFilesMatchAny = allFilesMatchAny.map(e => new PathFilter(e));
  }

  get allFilesMatchAny() {
    return this._allFilesMatchAny;
  }
}

/**
 * Filter class equivalent to the Python Filter
 */
class Filter {
  private _nameExpression: string;
  private _nameRegex: RegExp;
  private _files: PathFilter[];
  private _skipIf: SkipIf;
  private _cachedHash: string | null = null;
  /**
   * Creates a new Filter
   * @param {string} nameRegex - Regex pattern for job names
   * @param {string[]} files - List of file regex patterns
   * @param {SkipIf|null} skipIf - Optional skip-if condition
   */
  constructor(nameRegex: string, files: string[], skipIf: SkipIf | null = null) {
    this._nameExpression = nameRegex;
    this._nameRegex = new RegExp(nameRegex);
    this._files = files.map(e => new PathFilter(e));
    this._skipIf = skipIf || new SkipIf([]);
  }

  public matchesName(name: string): boolean {
    // console.log(`Filter '${this._nameExpression}' testing against name: '${name}': '${this._nameRegex}'`);
    return this._nameRegex.test(name);
  }

  get nameExpression() {
    return this._nameExpression;
  }


  /**
   * Check if a file matches any of the filters
   * @param {string} file - File path to check
   * @returns {boolean} - Whether the file matches any filter
   */
  public isMatchForFile(file: string): boolean {
    for (const pathFilter of this._files) {
      if (pathFilter.regex.test(file)) {
        // console.log(`Filter ${this._nameExpression} matched ${file} on ${pathFilter.expression}`);
        return true;
      }
    }
    return false;
  }

  /**
   * Check if any of the files match this filter
   * @param {string[]} files - List of files to check
   * @returns {boolean} - Whether any file matches and skip conditions are satisfied
   */
  public isMatch(files: string[]): boolean {
    let match = false;
    let allFilesMatchAnySkip = (
      this._skipIf !== null &&
      this._skipIf.allFilesMatchAny !== null
    );

    for (const file of files) {
      if (!match) { // only check for a match if we haven't found one yet
        if (this.isMatchForFile(file)) {
          match = true;
        }
      }

      if (allFilesMatchAnySkip) { // only check for skip if we haven't already had a non-match
        for (const skipFilter of this._skipIf.allFilesMatchAny) {
          const isSkipMatch = skipFilter.regex.test(file);
          if (!isSkipMatch) {
            console.log(
              `Filter ${this._nameExpression} skip-if failed to match ${file} on ${skipFilter.expression}`
            );
            allFilesMatchAnySkip = false;
            break;
          }
        }
      }
    }

    console.log(`Filter ${this._nameExpression} match: ${match}, allFilesMatchAnySkip: ${allFilesMatchAnySkip}`);
    const result = match && !allFilesMatchAnySkip;
    return result;
  }

  /**
   * Calculate hash based on the files that match the filter. The returned value is the hash of the names and contents of files that match the filter.
   * @param {string[]} files - List of files to check
   * @returns {string} - Hash digest
   */
  calculateHashFromFiles(files: string[]) {
    if (this._cachedHash !== null) {
      console.log(`Filter '${this._nameExpression}' hash already calculated: ${this._cachedHash}`);
      return this._cachedHash;
    }

    // Create a SHA-1 hash
    const hash = crypto.createHash('sha1');

    console.log(`::group::Hash files for filter '${this._nameExpression}'`);
    for (const file of files) {
      for (const pathFilter of this._files) {
        if (pathFilter.regex.test(file)) {
          // Add the filename to the hash
          hash.update(file);
          console.log(`- ${file}`);

          // Read and hash file contents
          const fileContent = fs.readFileSync(file);
          hash.update(fileContent);
          break;
        }
      }
    }
    console.log(`::endgroup::`);

    const hashValue = hash.digest('hex');
    console.log(`Filter '${this._nameExpression}' hash: ${hashValue}`);
    this._cachedHash = hashValue;
    return hashValue;
  }

  /**
   * Calculate hash based on the files with hashes that match the filter. The returned value is the hash of the name and hash of files that match the filter.
   * @param {FileWithHash[]} filesWithHashes - List of files with hashes to check
   * @returns {string} - Hash digest
   */
  calculateHashFromFilesWithHashes(filesWithHashes: FileWithHash[]) {
    if (this._cachedHash !== null) {
      console.log(`Filter '${this._nameExpression}' hash already calculated: ${this._cachedHash}`);
      return this._cachedHash;
    }

    // Create a SHA-1 hash
    const hash = crypto.createHash('sha1');

    console.log(`::group::Hash files for filter '${this._nameExpression}'`);
    for (const file of filesWithHashes) {
      for (const pathFilter of this._files) {
        if (pathFilter.regex.test(file.filename)) {
          // Add the filename to the hash
          hash.update(file.filename);
          console.log(`- ${file.filename}`);

          // Read and hash file contents
          hash.update(file.hash);
          break;
        }
      }
    }
    console.log(`::endgroup::`);

    const hashValue = hash.digest('hex');
    console.log(`Filter '${this._nameExpression}' hash: ${hashValue}`);
    this._cachedHash = hashValue;
    return hashValue;
  }
}

/**
 * Load filter file and parse YAML
 * @param {string} filterFile - Path to filter file
 * @returns {Filter[]} - Array of Filter objects
 */
function loadFilterFile(filterFile: string) {
  try {
    const fileContent = fs.readFileSync(filterFile, 'utf8');
    const filterData = yaml.parse(fileContent);

    if (filterData === null) {
      console.log(`Filter file ${filterFile} is empty.`);
      process.exit(1);
    }

    if (!Array.isArray(filterData)) {
      console.log(`Filter file ${filterFile} is not a list.`);
      process.exit(1);
    }

    const filters = [];
    for (const filterItem of filterData) {
      if (!('name' in filterItem)) {
        console.log(`Filter file ${filterFile} does not contain a name.`);
        process.exit(1);
      }
      if (!('files' in filterItem)) {
        console.log(`Filter file ${filterFile} does not contain a files list.`);
        process.exit(1);
      }
      if (!Array.isArray(filterItem.files)) {
        console.log(`Filter file ${filterFile} files list is not a list.`);
        process.exit(1);
      }
      if (filterItem.files.length === 0) {
        console.log(`Filter file ${filterFile} files list is empty.`);
        process.exit(1);
      }

      let skipIf = null;
      if ('skip-if' in filterItem) {
        if ('all-files-match-any' in filterItem['skip-if']) {
          skipIf = new SkipIf(filterItem['skip-if']['all-files-match-any']);
        }
      }

      const filter = new Filter(
        filterItem.name,
        filterItem.files,
        skipIf
      );
      filters.push(filter);
    }

    return filters;
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : 'Unknown error';
    console.error(`Error loading filter file: ${errorMessage}`);
    process.exit(1);
  }
}

/**
 * Get job list from workflow file
 * @param {string} jobFilename - Path to workflow file
 * @returns {string[]} - List of job names
 */
function getJobList(jobFilename: string) {
  try {
    const fileContent = fs.readFileSync(jobFilename, 'utf8');
    const jobData = yaml.parse(fileContent);

    if (jobData === null) {
      console.log(`Job file ${jobFilename} is empty.`);
      process.exit(1);
    }

    const jobs = jobData.jobs;
    if (jobs === undefined) {
      console.log(`Job file ${jobFilename} does not contain a jobs section.`);
      process.exit(1);
    }
    if (typeof jobs !== 'object' || jobs === null) {
      console.log(`Job file ${jobFilename} jobs section is not a dict.`);
      process.exit(1);
    }

    return Object.keys(jobs);
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : 'Unknown error';
    console.error(`Error loading job file: ${errorMessage}`);
    process.exit(1);
  }
}

/**
 * Recursively list files in a directory
 * @param {string} path - Directory path
 * @returns {string[]} - List of relative file paths
 */
function recursiveFileList(path: string) {
  const result: string[] = [];

  function processDir(dir: string, base: string) {
    const entries = fs.readdirSync(dir, { withFileTypes: true });

    for (const entry of entries) {
      if (entry.name === '.git') continue;

      const fullPath = `${dir}/${entry.name}`;
      if (entry.isDirectory()) {
        processDir(fullPath, base);
      } else {
        result.push(fullPath.substring(base.length + 1));
      }
    }
  }

  processDir(path, path);
  return result.sort();
}

export {
  PathFilter,
  SkipIf,
  Filter,
  loadFilterFile,
  getJobList,
  recursiveFileList
};
