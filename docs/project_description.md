# Project Description (Microsoft-Sponsored Capstone)

> **MCP Factory:** Research, design, and develop a method that produces an MCP server from an existing DLL, EXE, CMD, or repository.

## Project Overview

A successful implementation must be able to accept a binary compiled file such as a `fileA.dll` or `appB.exe` and profile it to determine what invocations it accepts and how to invoke it. Then generate an MCP architecture that allows AI agents to interact with it. 

Students may use de-compilers, profilers, help files, or scrape the web to enhance and augment the accuracy and efficacy of their MCP candidate. A successful project must demonstrate an ordinary executable or binary that lacks AI capabilities being put through the MCP factory, and an MCP implementation is then generated, and ready to accept invocations via an LLM such as Copilot.

## Sponsor Resources

The Microsoft sponsors will supply an Azure environment to develop the solution. The AI services will be monitored and should only be used within the scope of the project.

## Business Scenario

**Automated customer service** for the company Contoso.

---

## Section 1: Definition of a Binary or Executable

A file that is compiled and executable on Windows 11 or Win32, including:

- RPC, JNDI, COM/DCOM, SOAP, CORBA, JSON technologies
- Windows Registry entries (for hints and inventory of invocables)
- SQL source files
- JavaScript, Python, Ruby, PHP, and other JIT executables

## Section 2: Specifying the Target Binary

Users must be able to:

1. **Provide the system a copy** of the target file or an installed instance  
   - Example: `appC.exe` or `C:\Program Files\AppD\`
2. **Describe the file using free text** to give the system hints at what functions the executable is expected to expose

## Section 3: Displaying Functions and Invocations

Upon specifying the target file:

1. The system should display a **list of invocable features**
2. By default, all items are checked
3. Users may deselect some to reduce the set of invocable features that the generated MCP implementation exposes

## Section 4: Generating the MCP Architecture

1. Once the user has satisfied Sections 2 and 3, an interface to specify the **name of the generated component** is presented with a suggested name pre-populated
2. The system will generate the necessary components of the MCP architecture and deploy an instance for verification

## Section 5: Verifying the MCP Output

Upon completion of Sections 2–4:

1. User is presented with a **chat interface** to interact with the target application
2. The output of invoked executables is displayed in the conversation area
3. User can **download a copy** of the output

---

## Section 6: Sponsor Technical Requirements

Microsoft technologies and guidelines to incorporate:

| Technology | Usage |
|------------|-------|
| Azure (compute, storage, networking) | Cloud infrastructure |
| Azure OpenAI / AI Foundry | AI services |
| .NET Aspire | Application framework |
| VS Code, GitHub, GitHub Copilot, GitHub Spaces | Development tools |
| Microsoft Docs, Microsoft Learning | Reference materials (cite in README) |

**Constraints:**
- Cloud resources must not exceed **$150/month**
- All data must conform to **FERPA compliance**
- Azure resources restricted to project team only
- Unauthorized access reported

## Section 7: Communication Requirements

1. **Weekly meetings** (virtual or in-person, ≥30 minutes) with sponsor and Ken Christensen
2. **Email/Teams updates** for critical issues and key documents
3. **Fair delegation** of work among team members
