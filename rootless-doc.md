# Technical Investigation Report: Adapting a Privileged Binary for Secure Containerized Deployment

**Date:** April 28, 2025  
**Prepared by:** DevOps Engineering Team  
**Subject:** Analysis and Adaptation of a Privileged Binary for Non-Root Execution in a Containerized Environment ([How to Write Workplace Investigation Reports - HR Acuity](https://www.hracuity.com/blog/write-investigation-report/?utm_source=chatgpt.com))

---

## Executive Summary

This report outlines the technical investigation and adaptation process undertaken to securely deploy a customer-provided binary application, originally designed to run with root privileges, into our private cloud's containerized infrastructure. The primary objective was to enable the application to operate with the least necessary privileges, adhering to security best practices, while maintaining its intended functionality.

---

## 1. Background

- **Customer Requirement:** Deployment of an existing binary application within our private cloud environment.
- **Initial Conditions:** The binary was previously executed on a virtual machine with root privileges.
- **Security Objective:** Ensure the application runs with minimal necessary privileges to mitigate potential security risks.

---

## 2. Investigation Methodology

### 2.1 Binary Analysis

**Tools Utilized:**

- `file`: Determined the binary as an ELF 64-bit executable.
- `ldd`: Identified dynamic dependencies on shared libraries.
- `strings`: Revealed embedded messages, notably: "you must be a superuser to run this program".
- `objdump` and `readelf`: Analyzed ELF headers and sections for deeper insights.
- `sha256sum`: Computed checksum for integrity verification.
- `gdb`: Utilized for debugging, leveraging available symbol information. ([Software safety](https://en.wikipedia.org/wiki/Software_safety?utm_source=chatgpt.com), [Debugging Tips and Tricks: A Comprehensive Guide - Medium](https://medium.com/javarevisited/debugging-tips-and-tricks-a-comprehensive-guide-8d84a58ca9f2?utm_source=chatgpt.com))

**Findings:**

- The binary is a C language application relying on multiple shared libraries.
- Presence of debugging symbols facilitated in-depth analysis.
- Embedded checks enforce execution under root privileges. ([Software bug](https://en.wikipedia.org/wiki/Software_bug?utm_source=chatgpt.com), [Software Documentation Best Practices: A Comprehensive Guide](https://www.graphapp.ai/blog/software-documentation-best-practices-a-comprehensive-guide?utm_source=chatgpt.com))

### 2.2 Dependency Resolution

- Cataloged all shared object dependencies using `ldd`.
- Ensured all dependencies were available within the container environment. ([Debugging](https://en.wikipedia.org/wiki/Debugging?utm_source=chatgpt.com))

---

## 3. Containerization Process

### 3.1 Initial Container Build

- **Base Image:** Debian latest.
- **Inclusions:** The binary and all identified dependencies.
- **Execution:** Ran successfully with root privileges within the container. ([knowledgSoftware Documentation Best Practices [With Examples]](https://helpjuice.com/blog/software-documentation?utm_source=chatgpt.com), [How to Write Workplace Investigation Reports - HR Acuity](https://www.hracuity.com/blog/write-investigation-report/?utm_source=chatgpt.com))

### 3.2 Transition to Non-Root Execution

- Created a non-root user within the container.
- Attempted execution under this user resulted in the message: "you must be a superuser to run this program".
- `strace` analysis showed no system-level permission errors, indicating the check was internal to the application. ([Tracing (software)](https://en.wikipedia.org/wiki/Tracing_%28software%29?utm_source=chatgpt.com))

---

## 4. Privilege Check Circumvention

### 4.1 Strategy

- Identified that the application uses `geteuid()` and `getuid()` system calls to verify root privileges.
- Decided to override these calls to simulate root execution.

### 4.2 Implementation

- **Custom Shared Library:** Developed a shared library overriding `geteuid()` and `getuid()` to return 0.
- **Compilation:** Used `gcc` with `-shared` and `-fPIC` flags.
- **Execution:** Preloaded the custom library using the `LD_PRELOAD` environment variable.

### 4.3 Outcome

- The application proceeded past the internal root check and began execution.
- Subsequent `strace` analysis revealed a failure in creating a raw socket:
  ```
  
socket(AF_INET, SOCK_RAW, htons(ETH_P_ALL)) = -1 EPERM (Operation not permitted)
  ```


---

## 5. Capability Adjustment

- **Issue:** The application requires the ability to create raw sockets, which is restricted for non-root users.
- **Solution:** Granted the container the `CAP_NET_RAW` capability during execution:
  ```bash
  docker run --rm --cap-add=NET_RAW -it mybinary-test
  ```


---

## 6. Final Configuration

- **User:** Non-root user with UID 10000.
- **Environment:** `LD_PRELOAD` set to the path of the custom shared library.
- **Capabilities:** Container granted `CAP_NET_RAW`.
- **Result:** Application runs successfully without full root privileges.

---

## 7. Next Steps

- **Deployment:** Integrate the container into the Kubernetes cluster.
- **Helm Chart:** Develop a Helm chart to facilitate deployment and customization.
- **Monitoring:** Implement a Prometheus exporter to expose application metrics for monitoring purposes.

---

## 8. Conclusion

Through systematic analysis and strategic overrides, we successfully adapted a root-dependent binary to operate securely within a containerized environment under non-root privileges, aligning with best practices for security and maintainability.

--- 
