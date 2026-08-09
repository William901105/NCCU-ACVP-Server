using System;
using System.Collections.Generic;
using System.Linq;
using NIST.CVP.ACVTS.Libraries.Common;
using NIST.CVP.ACVTS.Libraries.Common.ExtensionMethods;
using NIST.CVP.ACVTS.Libraries.Common.Helpers;
using NIST.CVP.ACVTS.Libraries.Crypto.Common.DRBG.Enums;
using NIST.CVP.ACVTS.Libraries.Crypto.Common.DRBG.Helpers;
using NIST.CVP.ACVTS.Libraries.Crypto.Common.Math;
using NIST.CVP.ACVTS.Libraries.Generation.Core;
using NIST.CVP.ACVTS.Libraries.Math;

namespace NIST.CVP.ACVTS.Libraries.Generation.DRBG.SP800_90Ar1
{
    public class ParameterValidator : ParameterValidatorBase, IParameterValidator<Parameters>
    {
        private static int MaxOutputSize = 4096;

        public ParameterValidateResponse Validate(Parameters parameters)
        {
            DrbgAttributes attributes = null;
            var errorResults = new List<string>();

            var algoModeRevision =
                AlgoModeHelpers.GetAlgoModeFromAlgoAndMode(parameters.Algorithm, parameters.Mode, parameters.Revision);

            if (parameters.PredResistanceEnabled == null)
            {
                errorResults.Add("predResistance array must be provided.");
                return new ParameterValidateResponse(errorResults);
            }

            if (parameters.PredResistanceEnabled.Length != 1 && parameters.PredResistanceEnabled.Length != 2)
            {
                errorResults.Add("predResistance must be a minimal array of booleans");
            }

            if (parameters.PredResistanceEnabled.Distinct().Count() != parameters.PredResistanceEnabled.Length)
            {
                errorResults.Add("predResistance must have distinct elements");
            }

            foreach (var capability in parameters.Capabilities)
            {
                if (new[] { AlgoMode.hashDRBG_SP800_90Ar1, AlgoMode.hmacDRBG_SP800_90Ar1 }.Contains(algoModeRevision) &&
                    capability.DerFuncEnabled)
                {
                    errorResults.Add("The derFuncEnabled property is not valid for HASH and HMAC DRBG testing.");
                    continue;
                }

                ValidateAndGetOptions(parameters, capability, errorResults, ref attributes);

                // Cannot validate the rest of the parameters as they are dependent on the successful validation of the mechanism and mode.
                if (errorResults.Count > 0)
                {
                    return new ParameterValidateResponse(errorResults);
                }

                ValidateEntropyAndNonce(algoModeRevision, capability, attributes, errorResults);
                ValidatePersonalizationString(capability, attributes, errorResults);
                ValidateAdditionalInput(capability, attributes, errorResults);

                var baseOutputLength = 0;

                if (attributes.Mechanism == DrbgMechanism.Counter)
                { 
                    ValidateCounterFieldLength(capability, errorResults, ref attributes);
                    baseOutputLength = DrbgAttributesHelper.GetCounterDrbgAttributes(attributes.Mode).OutputLength;
                    // check if any errors were found during the validation of the counterFieldLen. If so, return the errors.
                    // This must be done because the validation of returnedBitsLen relies on a valid value for counterFieldLen.
                    if (errorResults.Count > 0)
                    {
                        return new ParameterValidateResponse(errorResults);
                    }
                }
                else if (attributes.Mechanism == DrbgMechanism.Hash || attributes.Mechanism == DrbgMechanism.HMAC)
                {
                    baseOutputLength = DrbgAttributesHelper.GetHashDrbgAttributes(attributes.Mode).OutputLength;
                }
                
                ValidateReturnedBitsLen(capability, errorResults, baseOutputLength, parameters.Algorithm, ref attributes);
            }

            return new ParameterValidateResponse(errorResults);
        }

        private void ValidateAndGetOptions(Parameters parameters, Capability capability, List<string> errorResults, ref DrbgAttributes attributes)
        {
            try
            {
                attributes = DrbgAttributesHelper.GetDrbgAttributes(parameters.Algorithm, capability.Mode, capability.DerFuncEnabled);
            }
            catch (ArgumentException)
            {
                errorResults.Add("Invalid Algorithm/Mode provided.");
                return;
            }

            if (attributes.Mechanism != DrbgMechanism.Counter && capability.DerFuncEnabled)
            {
                errorResults.Add("Derivation Function not supported for hash/hmac based drbgs");
            }
        }

        private void ValidateEntropyAndNonce(AlgoMode algoModeRevision, Capability capability, DrbgAttributes attributes, List<string> errorResults)
        {
            var entropySegmentCheck = ValidateSegmentCountGreaterThanZero(capability.EntropyInputLen, "Entropy Domain");
            errorResults.AddIfNotNullOrEmpty(entropySegmentCheck);
            var nonceSegmentCheck = ValidateSegmentCountGreaterThanZero(capability.NonceLen, "Nonce Domain");
            errorResults.AddIfNotNullOrEmpty(nonceSegmentCheck);
            if (!string.IsNullOrEmpty(entropySegmentCheck) || !string.IsNullOrEmpty(nonceSegmentCheck))
            {
                return;
            }

            var entropyFullDomain = capability.EntropyInputLen.GetDomainMinMax();
            var nonceFullDomain = capability.NonceLen.GetDomainMinMax();

            // 1) Verify the supplied entropy input lengths, i.e., is the supplied entropyInputLen within the valid range of entropy input len values?
            var entropyRangeCheck = ValidateRange(
                new long[] { entropyFullDomain.Minimum, entropyFullDomain.Maximum },
                attributes.MinEntropyInputLength,
                attributes.MaxEntropyInputLength,
                "Entropy Range"
            );
            errorResults.AddIfNotNullOrEmpty(entropyRangeCheck);

            // 2) Perform checks to verify that the supplied nonce lengths are valid
            // 2a.) Drbgs/scenarios where nonces are prohibited/not used (a nonceLen range of 0 should be supplied to indicate this)
            if (algoModeRevision == AlgoMode.ctrDRBG_SP800_90Ar1 && !capability.DerFuncEnabled)
            {
                var nonceCheckCtrDrbgDerFuncFalse = ValidateRange(
                    new long[] { nonceFullDomain.Minimum, nonceFullDomain.Maximum },
                    attributes.MinNonceLength,
                    attributes.MaxNonceLength,
                    $"Nonce Range for {capability.Mode}"
                );
                
                errorResults.AddIfNotNullOrEmpty(nonceCheckCtrDrbgDerFuncFalse);
            }
            else
            {
                // 2b.) Drbgs/scenarios where nonces are required.
                // Ordinarily, SP 800-90Ar1 requires that nonce's contain at least 1/2 * security strength bits of entropy and
                // that the entropy input contain at least security strength bits of entropy. We would ordinarily check that
                // the smallest value supplied for nonceLen is >= 1/2 * security strength bits, but SP 800-90Ar1 actually isn't that strict. 
                // What it really cares about is that the entropy input + nonce contains 3/2 * security strength bits of entropy.
                // So, instead of checking that nonceLen is >= 1/2 * security strength bits, what we really want to check is that 
                // the smallest value supplied for entropyInputLen + the smallest value supplied for nonceLen is >= 3/2 * security strength bits.
                if (entropyFullDomain.Minimum + nonceFullDomain.Minimum < attributes.MinEntropyInputLength + attributes.MinNonceLength)
                    errorResults.Add($"The supplied min entropyInputLen ({entropyFullDomain.Minimum}) + the supplied min nonceLen ({nonceFullDomain.Minimum}) must be >= 3/2 security strength bits or {attributes.MinEntropyInputLength + attributes.MinNonceLength} bits, but is {entropyFullDomain.Minimum + nonceFullDomain.Minimum} bits.");

                // also verify that the supplied nonceLens do not exceed the maximum allow nonceLens
                var nonceMaxCheck = ValidateRange(
                    new long[] { nonceFullDomain.Maximum },
                    0,
                    attributes.MaxNonceLength,
                    $"Nonce Max for {capability.Mode}"
                );

                errorResults.AddIfNotNullOrEmpty(nonceMaxCheck);
            }
            
            var entropyModCheck = ValidateMultipleOf(capability.EntropyInputLen, 8, "Entropy Modulus");
            errorResults.AddIfNotNullOrEmpty(entropyModCheck);
            
            var nonceModCheck = ValidateMultipleOf(capability.NonceLen, 8, "Nonce Modulus");
            errorResults.AddIfNotNullOrEmpty(nonceModCheck);
        }
        
        private void ValidatePersonalizationString(Capability capability, DrbgAttributes attributes, List<string> errorResults)
        {
            var segmentCheck = ValidateSegmentCountGreaterThanZero(capability.PersoStringLen, "Personalization String Domain");
            errorResults.AddIfNotNullOrEmpty(segmentCheck);
            if (!string.IsNullOrEmpty(segmentCheck))
            {
                return;
            }

            var personalizationStringFullDomain = capability.PersoStringLen.GetDomainMinMax();

            var rangeCheck = ValidateRange(
                new long[] { personalizationStringFullDomain.Minimum, personalizationStringFullDomain.Maximum, },
                0,
                attributes.MaxPersonalizationStringLength,
                "Personalization String Range"
            );
            errorResults.AddIfNotNullOrEmpty(rangeCheck);

            var modCheck = ValidateMultipleOf(capability.PersoStringLen, 8, "Personalization String Modulus");
            errorResults.AddIfNotNullOrEmpty(modCheck);
        }

        private void ValidateAdditionalInput(Capability capability, DrbgAttributes attributes, List<string> errorResults)
        {
            var segmentCheck = ValidateSegmentCountGreaterThanZero(capability.AdditionalInputLen, "Additional Input Domain");
            errorResults.AddIfNotNullOrEmpty(segmentCheck);
            if (!string.IsNullOrEmpty(segmentCheck))
            {
                return;
            }

            var additionalInputFullDomain = capability.AdditionalInputLen.GetDomainMinMax();

            var rangeCheck = ValidateRange(new long[] { additionalInputFullDomain.Minimum, additionalInputFullDomain.Maximum, },
                0,
                attributes.MaxAdditionalInputStringLength,
                "Additional Input Range"
            );
            errorResults.AddIfNotNullOrEmpty(rangeCheck);

            var modCheck = ValidateMultipleOf(capability.AdditionalInputLen, 8, "Additional Input Modulus");
            errorResults.AddIfNotNullOrEmpty(modCheck);
        }

        private void ValidateReturnedBitsLen(Capability capability, List<string> errorResults, int minimumOutputLength, string algo, ref DrbgAttributes attributes)
        {
            var segmentCheck = ValidateSegmentCountGreaterThanZero(capability.ReturnedBitsLen, $"{nameof(capability.ReturnedBitsLen)} Domain");
            errorResults.AddIfNotNullOrEmpty(segmentCheck);
            if (!string.IsNullOrEmpty(segmentCheck))
            {
                return;
            }
            
            var modCheck = ValidateMultipleOf(capability.ReturnedBitsLen, BitString.BITSINBYTE, $"{nameof(capability.ReturnedBitsLen)} Modulus");
            errorResults.AddIfNotNullOrEmpty(modCheck);

            var returnedBitsLenDomainMinMax = capability.ReturnedBitsLen.GetDomainMinMax();
            
            // The minimum value of returnedBitsLen seems to be outlen (Output Block Length). outlen is defined in
            // Table 2 for hash and hmac drbgs and in Table 3 (see blocklen) for ctr drbgs.  
            if (returnedBitsLenDomainMinMax.Minimum < minimumOutputLength)
            {
                errorResults.Add($"Requested {nameof(capability.ReturnedBitsLen)} of {returnedBitsLenDomainMinMax.Minimum} is below the minimum allowed length of {minimumOutputLength}");
            }

            // For hash and hmac drbgs, per SP800-90Ar1 Table 2, the maximum allowed value of returnedBitsLen is 2^19 bits.
            // For ctr drbgs, per Table 3, the maximum value of returnedBitsLen is min(B, 2^19) bits for AES and min(B, 2^13)
            // bits for TDES where B = (2^ctr_len - 4) x blocklen.
            
            // As values such as 2^19 and 2^13 are quite large, we arbitrarily cap the maximum value of returnedBitsLen
            // at MaxOutputSize or 4096 bits.
            var maxOutputSize = MaxOutputSize;
            
            if (algo.Contains("ctr"))
            {
                // if the algorithm is ctrDRBG, then calculate B
                var B = (NumberTheory.Pow2((int) capability.CounterFieldLen) - 4) * DrbgAttributesHelper.GetCounterDrbgAttributes(attributes.Mode).BlockSize;
                // if B is less than MaxOutputSize, then set maxOutputSize to B following min(B, 2^19) bits for AES and
                // min(B, 2^13) bits for TDES 
                if (B < MaxOutputSize)
                {
                    // ensure we can cast B to an int
                    if (B >= int.MinValue && B <= int.MaxValue)
                        maxOutputSize = (int) B;
                }
            }            
            
            if (returnedBitsLenDomainMinMax.Maximum > maxOutputSize)
            {
                errorResults.Add($"Requested {nameof(capability.ReturnedBitsLen)} of {returnedBitsLenDomainMinMax.Maximum} exceeds maximum allowed length of {maxOutputSize}");
            }
        }
        
        private void ValidateCounterFieldLength(Capability capability, List<string> errorResults, ref DrbgAttributes attributes)
        { 
            var attr = DrbgAttributesHelper.GetCounterDrbgAttributes(attributes.Mode);
            
            // counterFieldLen is required for ctrDRBG.
            if (capability.CounterFieldLen == null)
            {
                errorResults.Add($"No {nameof(capability.CounterFieldLen)} provided. The {nameof(capability.CounterFieldLen)} " +
                                 $"property is required and must be provided.");
            }
            
            // Per SP 800-90A Table 3, 4 ≤ ctr_len ≤ blocklen. blocklen is 128 for AES modes and 64 for TDES.
            if (capability.CounterFieldLen < 4)
            {
                errorResults.Add($"Requested {nameof(capability.CounterFieldLen)} of {capability.CounterFieldLen} " +
                                 $"is < 4. Per SP 800-90A Table 3, {nameof(capability.CounterFieldLen)} " +
                                 $"must satisfy 4 <= {nameof(capability.CounterFieldLen)} <= {attr.BlockSize}.");
            }
            if (capability.CounterFieldLen > attr.BlockSize)
            {
                errorResults.Add($"Requested {nameof(capability.CounterFieldLen)} of {capability.CounterFieldLen} " +
                                 $"is > {attr.BlockSize}. Per SP 800-90A Table 3, {nameof(capability.CounterFieldLen)} " +
                                 $"must satisfy 4 <= {nameof(capability.CounterFieldLen)} <= {attr.BlockSize}.");
            }
        }
    }
}
