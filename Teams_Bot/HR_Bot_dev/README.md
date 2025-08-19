# HR Bot

A Microsoft Teams bot application designed to streamline HR operations through intelligent resume management, candidate search, and automated resume generation.

## Overview

HR Bot is a comprehensive Teams application that integrates with NiFi processors to provide automated HR services. It enables HR professionals to manage candidate resumes, search for qualified candidates, generate tailored resumes, and perform bulk operations through an intuitive chat interface.

## Features

### Core Functionality
- **Resume Management**: Add, view, and delete candidate resumes
- **Intelligent Search**: Find candidates by name, skills, or keywords
- **Resume Generation**: Create tailored resumes with or without job descriptions
- **Bulk Operations**: Upload multiple resumes from SharePoint folders
- **Candidate Scoring**: AI-powered candidate evaluation and ranking

### Commands

| Command | Description | Usage |
|---------|-------------|-------|
| `/makeresume` | Generate or tailor a resume | `/makeresume <employee_id>` or `/makeresume <name> jd "job description"` |
| `/search` | Search for candidates | `/search <query>` |
| `/view` | View candidate resume | `/view <employee_id>` or `/view <name>` |
| `/delete` | Delete candidate | `/delete <employee_id>` or `/delete name <name>` |
| `/add` | Add new candidate | `/add <employee_id>` |
| `/uploadfolder` | Bulk upload resumes | `/uploadfolder <sharepoint_folder_link>` |
| `/help` | Show available commands | `/help` |
| `/test` | Test connectivity | `/test` |
| `/reset` | Reset conversation state | `/reset` |

## Architecture

### Technology Stack
- **Frontend**: Microsoft Teams Adaptive Cards
- **Backend**: Node.js with Microsoft Agents Hosting
- **Storage**: Memory-based conversation state
- **Integration**: NiFi processors for backend operations
- **Authentication**: Microsoft Graph API integration

### System Components
- **Teams Bot Interface**: Handles user interactions and displays information
- **NiFi Integration**: Processes resume data and generates documents
- **Graph API**: Manages OneDrive file operations
- **Fallback System**: Ensures reliability with primary and backup NiFi endpoints

## Installation

### Prerequisites
- Node.js 18, 20, or 22
- Microsoft Teams account
- NiFi processor endpoints
- Microsoft Graph API access

### Setup
1. Clone the repository
2. Install dependencies:
   ```bash
   npm install
   ```
3. Configure environment variables:
   ```bash
   PRIMARY_NIFI_URL=<primary_nifi_endpoint>
   FALLBACK_NIFI_URL=<fallback_nifi_endpoint>
   ```
4. Start the application:
   ```bash
   npm start
   ```

### Development
```bash
npm run dev          # Start with nodemon
npm run dev:teamsfx  # Start with Teams Toolkit
```

## Configuration

### Environment Variables
- `PRIMARY_NIFI_URL`: Primary NiFi processor endpoint
- `FALLBACK_NIFI_URL`: Backup NiFi processor endpoint
- Additional Graph API configuration as required

### NiFi Integration
The bot communicates with NiFi processors for:
- Resume parsing and storage
- Candidate search and scoring
- Document generation
- Bulk operations

## Usage Examples

### Adding a New Candidate
```
/add 12345
[Bot prompts for SharePoint resume link]
[User provides link]
[Bot confirms and uploads]
```

### Generating a Tailored Resume
```
/makeresume John Doe jd "Senior Software Engineer with 5+ years experience in Node.js and React"
```

### Searching for Candidates
```
/search "Python developer with machine learning experience"
```

### Bulk Upload
```
/uploadfolder https://company.sharepoint.com/sites/hr/Shared%20Documents/Resumes
```

## Security Features

- **Authentication**: Microsoft Teams authentication
- **Authorization**: Role-based access control
- **Data Privacy**: Secure handling of candidate information
- **Audit Trail**: Conversation state management

## Error Handling

The bot includes comprehensive error handling for:
- Network connectivity issues
- Invalid user input
- NiFi processor failures
- File upload errors
- Authentication failures

## Performance

- **Response Time**: Optimized for real-time interactions
- **Scalability**: Memory-based state management
- **Reliability**: Fallback endpoint support
- **Caching**: Efficient data retrieval and storage

## Support

For technical support or feature requests, please contact the development team or create an issue in the repository.



