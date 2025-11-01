# Docs TODO

## Should have

- [ ] Langchain for Python SDK
- [ ] Clarify SSL requirements for SDKs

## Nice-to-haves

- [ ] Add backing stores to `v0.12.x/integrations` section
- [ ] Change voice from 1st-person to 3rd-person (we/our -> Cyborg/Cyborg's)
- [ ] Add performance benchmarks
- [ ] Replace boilerplate "Exceptions" with language-specific exceptions in SDK docs
- [ ] Cross-reference all return formats/types across SDKs & harmonize using contract tests
- [ ] Add SSL/TLS configuration guidance for production PostgreSQL deployments (intro/backing-stores.mdx)
- [ ] Add practical code example showing encryption/decryption flow (intro/encryption.mdx)
- [ ] Add troubleshooting sections to major guides
- [ ] Add performance tuning guidelines for production deployments
- [ ] Create migration guides from other vector DBs (Pinecone, Chroma, FAISS)
- [ ] Add comprehensive RAG pipeline examples for LangChain integration

### Code Examples & Clarity

#### Go SDK
- [ ] Add more comprehensive error handling examples
- [ ] Test all Go examples for compilation
- [ ] Add performance benchmarking guide

#### JavaScript/TypeScript
- [ ] Add more Buffer handling examples and documentation
- [ ] Document async patterns more thoroughly
- [ ] Add version compatibility note (e.g., "Compatible with langchain-core >= 0.2.0")

#### C++
- [ ] Add thread-safety documentation (if applicable)
- [ ] Add memory management guidance (unique_ptr vs raw pointers)
- [ ] Add performance notes to methods like Train() and Query()
- [ ] Create a "Migration from Python" guide for C++ users

#### Python
- [ ] Add note about cache size units (bytes vs megabytes) - clarify in create-index and load-index docs
- [ ] Add examples of multi-tenancy use cases in encrypted-indexes/introduction.mdx
- [ ] Add `query_contents` parameter to embedded/python/encrypted-index/query.mdx parameter table

### Consistency & Standardization

- [ ] Standardize embedding model paths (use full HuggingFace paths like "sentence-transformers/all-MiniLM-L6-v2" vs short names "all-MiniLM-L6-v2")
- [ ] Clarify DBConfig constructor usage pattern (positional vs keyword arguments)
- [ ] Add cross-reference table showing C++ ↔ Python method equivalents
- [ ] Document GPUConfig differences between Python and C++ more prominently
- [ ] Standardize index type string format (ivf_flat vs ivfflat) across JS/TS SDK

### API Documentation

#### REST API
- [ ] Add example error response bodies to all exception sections
- [ ] Add API rate limiting documentation (if applicable)
- [ ] Add pagination documentation (if list endpoints support it)
- [ ] Add API versioning/deprecation policy
- [ ] Consider adding OpenAPI/Swagger spec generation from docs
- [ ] Complete describe-index.mdx exceptions section

#### Service-specific
- [ ] Add use cases to get-vector-count.mdx for consistency
- [ ] Document the extra Client constructor parameters in C++ (e.g., `0, false` parameters)

### General Improvements

- [ ] Add "Common Mistakes" or "Common Pitfalls" sections to major methods
- [ ] Verify JavaScript SDK package name `@cyborgdb/client` against actual npm package
- [ ] Verify C++ API against actual library implementation
- [ ] Replace placeholder vector values `[1, 2, 3, ...]` with realistic examples or mark as pseudocode
- [ ] Add more complex, real-world examples throughout
- [ ] Verify embedding model short names vs. full paths support