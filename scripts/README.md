# Scripts Directory

This directory contains utility scripts for post-processing and analysis of scraping runs.

## Branch Walker (`branch_walker.py`)

**Purpose**: Visualizes the complete content lineage from a scraping run, showing how content was discovered and scraped in a hierarchical story format.

**What it does**:
- Walks through one complete branch of a scraping run from root URL to deepest leaf
- Shows the actual content extracted at each step
- Displays links discovered and which ones led to the next page
- Creates a markdown report telling the linear story of content discovery

### Usage

```bash
# List available branches for a run
python scripts/branch_walker.py <run_id> --list-branches

# Generate markdown report for first branch (prints to stdout)
python scripts/branch_walker.py <run_id>

# Generate report for specific branch and save to file
python scripts/branch_walker.py <run_id> --branch-index 2 --output reports/my_report.md
```

### Examples

```bash
# See what branches are available
python scripts/branch_walker.py 36a211b7-20f5-453a-8adb-a523691bf9eb --list-branches

# Generate detailed report for React blog scraping
python scripts/branch_walker.py 36a211b7-20f5-453a-8adb-a523691bf9eb --output reports/react_analysis.md

# Analyze a different branch from the same run
python scripts/branch_walker.py 36a211b7-20f5-453a-8adb-a523691bf9eb --branch-index 5 --output reports/react_branch_5.md
```

### Sample Output Structure

The generated markdown report includes:

1. **Run Overview**: Basic information about the scraping run
2. **Step-by-Step Analysis**: For each page in the branch:
   - URL, status code, domain, parent relationship
   - Page title and meta description
   - Content preview (first 800 characters)
   - All links discovered on the page
   - Which specific link led to the next page in the chain
   - Key HTTP response headers
   - Any errors encountered
3. **Branch Summary**: Statistics about the complete path

### Use Cases

- **Quality Assurance**: Verify the scraper is following the right content paths
- **Content Analysis**: Understand what content is being extracted at each step
- **Debugging**: Trace exactly how the scraper navigated from page to page
- **Demonstrations**: Show stakeholders the linear story of content discovery
- **Process Optimization**: Identify inefficient crawling patterns or missed content

### Requirements

- Must be run after a scraping session has completed
- Requires the run ID from a successful scraping run
- Content files must be available in the expected directory structure
- Database must contain the page relationship data

### Technical Details

- Automatically finds the deepest branches (maximum crawl depth reached)
- Handles multiple root URLs and complex link hierarchies
- Loads actual saved content from disk for detailed analysis
- Supports both file output and stdout printing
- Graceful error handling for missing or corrupted content files
