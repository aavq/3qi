# Adapting a privileged binary for secure containerized deployment

**Date:** 28 April 2025
**Prepared by:** IB FIC HC Team
**Subject:** Analysis and adaptation of a privileged binary for rootless execution in a containerized environment

---

## Executive Summary

This document include a technical investigation and adaptation process undertaken to securely deploy a customer-provided binary application, originally designed to run with root privileges, into our Hybrid Private Cloud containerized infrastructure. The primary objective was to enable the application to operate with the least necessary privileges, adhering to security best practices, while maintaining its intended functionality.

---

## 1. Background

* **Customer Requirement:** Deployment of an existing binary application within our Private Cloud environment.
* **Initial Conditions:** The binary was previously executed on a virtual machine with root privileges.
* **Security Objective:** Ensure the application runs with minimal necessary privileges to mitigate potential security risks.

---

## 2. Investigation methodology

### 2.1 The binary analysis

**Tools and utilities:**

* `file`: Determined the binary as an ELF 64-bit executable.
* `ldd`: Identified dynamic dependencies on shared libraries as know as shared objects.
* `strings`: Revealed embedded messages, notably: "you must be a superuser to run this program".
* `objdump` and `readelf`: Analyzed ELF headers and sections for deeper insights.
* `sha256sum`: Computed checksum for integrity verification.
* `gdb`: Utilized for debugging, leveraging available symbol information.

**Findings:**

* The binary is a C language application relying on multiple shared libraries.
* The presence of debugging symbols facilitated in-depth analysis.
* Integrated checks enforce execution under root privileges.

### 2.2 Dependency resolution

* Cataloged all shared object dependencies using `ldd`.
* Ensured all dependencies were available within the container environment.

---

## 3. Containerization process

### 3.1 Initial container build

* **Base Image:** RHEL 8 latest.
* **Inclusions:** The binary and all identified dependencies.
* **Execution:** Ran successfully with root privileges within the container.

### 3.2 Transition to rootless execution

* Created a rootless user within the container.
* Attempted execution under this user resulted in the message: "you must be a superuser to run this program".
* `strace` analysis showed no system-level permission errors, indicating the check was internal to the application.

---

## 4. Privilege check workaround

### 4.1 Strategy

* Identified that the application uses `geteuid()` and `getuid()` system calls to verify root privileges.
* Decided to override these calls to simulate root execution.

### 4.2 Implementation

* **Custom Shared Library:** Developed a shared library overriding `geteuid()` and `getuid()` to return 0.
* **Compilation:** Used `gcc` with `-shared` and `-fPIC` flags.
* **Execution:** Preloaded the custom library using the `LD_PRELOAD` environment variable.

### 4.3 Outcome

* The application proceeded past the internal root check and began execution.
* Subsequent `strace` analysis revealed a failure in creating a raw socket:

```log
socket(AF_INET, SOCK_RAW, htons(ETH_P_ALL)) = -1 EPERM (Operation not permitted)
```

## 5. Capability adjustment

- **Issue:** SOCK_RAW - Operation not permitted
- **Solution:** Add the capability - NET_RAW


```bash
podman run --cap-add=NET_RAW --name mybinary --rm -it mybinaryiamge:firstversion
````

---

## 6. Final configuration

* **User:** rootless user with UID 10000.
* **Environment:** `LD_PRELOAD` set to the path of the custom shared library.
* **Capabilities:** Container granted `CAP_NET_RAW`.
* **Result:** Application runs successfully without full root privileges.

---

## 7. Next steps

* **Deployment:** Integrate the container into the Kubernetes cluster.
* **Helm Chart:** Develop a Helm chart to facilitate deployment and customization.
* **Monitoring:** Implement a prometheus exporter to expose application metrics for monitoring purposes.

---

## 8. Conclusion

Through systematic analysis and strategic overrides, a root-dependent binary has been successfully adapted to operate securely within a containerized environment under rootless privileges, aligning with best practices for security and maintainability.

---
