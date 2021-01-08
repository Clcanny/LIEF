/* Copyright 2017 R. Thomas
 * Copyright 2017 Quarkslab
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
#ifndef LIEF_PE_SIGNATURE_H_
#define LIEF_PE_SIGNATURE_H_

#include "LIEF/Object.hpp"
#include "LIEF/visibility.h"

#include "LIEF/PE/signature/x509.hpp"
#include "LIEF/PE/signature/SignerInfo.hpp"
#include "LIEF/PE/signature/ContentInfo.hpp"

#include "LIEF/PE/signature/types.hpp"
#include "LIEF/PE/enums.hpp"
#include "LIEF/enums.hpp"

namespace LIEF {
namespace PE {

class SignatureParser;
class Binary;

//! Main interface for the PKCS #7 signature scheme
class LIEF_API Signature : public Object {

  friend class SignatureParser;
  friend class Parser;
  friend class Binary;

  public:
  //! Hash the input given the algorithm
  static std::vector<uint8_t> hash(const std::vector<uint8_t>& input, ALGORITHMS algo);

  public:
  //! Flags returned by verification fonctions
  enum class VERIFICATION_FLAGS {
    OK = 0,
    INVALID_SIGNER                = 1 << 0,
    UNSUPPORTED_ALGORITHM         = 1 << 1,
    INCONSISTENT_DIGEST_ALGORITHM = 1 << 2,
    CERT_NOT_FOUND                = 1 << 3,
    CORRUPTED_CONTENT_INFO        = 1 << 4,
    CORRUPTED_AUTH_DATA           = 1 << 5,
    MISSING_PKCS9_MESSAGE_DIGEST  = 1 << 6,
    BAD_DIGEST                    = 1 << 7,
    BAD_SIGNATURE                 = 1 << 8,
    NO_SIGNATURE                  = 1 << 9,
  };

  Signature(void);
  Signature(const Signature&);
  Signature& operator=(const Signature&);

  //! Should be 1
  uint32_t version(void) const;

  //! Algorithm used to *digest* the file.
  //!
  //! It should match SignerInfo::digest_algorithm
  inline ALGORITHMS digest_algorithm() const {
    return this->digest_algorithm_;
  }

  //! Return the ContentInfo
  const ContentInfo& content_info(void) const;

  //! Return an iterator over x509 certificates
  it_const_crt certificates(void) const;

  //! Return an iterator over the signers (SignerInfo) defined in the PKCS #7 signature
  it_const_signers_t signers(void) const;

  //! Return the raw original PKCS7 signature
  const std::vector<uint8_t>& raw_der(void) const;

  virtual void accept(Visitor& visitor) const override;

  //! Check if this signature is valid according to the Authenticode/PKCS #7 verification scheme
  //!
  //! 1. It must contain only **one** signer info
  //! 2. Signature::digest_algorithm must match:
  //!    * ContentInfo::digest_algorithm
  //!    * SignerInfo::digest_algorithm
  //! 3. The x509 certificate specified by SignerInfo::serial_number **and** SignerInfo::issuer
  //!    must exist within Signature::certificates
  //! 4. Given the x509 certificate, compare SignerInfo::encrypted_digest against either:
  //!    * hash of authenticated attributes if present
  //!    * hash of ContentInfo
  //! 5. If they are Authenticated attributes, check that a PKCS9_MESSAGE_DIGEST attribute exists
  //!    and that its value matches hash of ContentInfo
  VERIFICATION_FLAGS check() const;

  virtual ~Signature(void);

  LIEF_API friend std::ostream& operator<<(std::ostream& os, const Signature& signature);

  private:

  uint32_t                version_ = 0;
  ALGORITHMS              digest_algorithm_ = ALGORITHMS::UNKNOWN;
  ContentInfo             content_info_;
  std::vector<x509>       certificates_;
  std::vector<SignerInfo> signers_;

  uint64_t                content_info_start_ = 0;
  uint64_t                content_info_end_ = 0;

  uint64_t                auth_start_ = 0;
  uint64_t                auth_end_ = 0;

  std::vector<uint8_t> original_raw_signature_;
};


}
}

ENABLE_BITMASK_OPERATORS(LIEF::PE::Signature::VERIFICATION_FLAGS);


#endif

