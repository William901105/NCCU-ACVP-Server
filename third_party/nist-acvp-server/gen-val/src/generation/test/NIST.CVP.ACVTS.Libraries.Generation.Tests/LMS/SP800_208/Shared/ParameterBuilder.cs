using NIST.CVP.ACVTS.Libraries.Crypto.Common.Asymmetric.LMS.Native.Enums;
using NIST.CVP.ACVTS.Libraries.Generation.LMS.SP800_208.Shared;
using NIST.CVP.ACVTS.Libraries.Math.Domain;

namespace NIST.CVP.ACVTS.Libraries.Generation.Tests.LMS.SP800_208.Shared
{
    /// <summary>
    /// Fluent builder for <see cref="Parameters"/> used in LMS SP800-208 tests.
    /// Mirrors the builder pattern used for other algorithms.
    /// </summary>
    public class ParameterBuilder
    {
        private string _algorithm = "LMS";
        private string _mode = "sigGen"; // default to sigGen
        private string _revision = "SP800-208";
        private MathDomain _messageLength = new MathDomain().AddSegment(new ValueDomainSegment(256));
        private GeneralCapabilities _generalCapabilities;
        private SpecificCapability[] _specificCapabilities;

        // By default creates a builder with general capabilities (a matching pair).
        public ParameterBuilder(bool specific = false)
        {
            if (specific)
            {
                _specificCapabilities =
                [
                    new SpecificCapability
                    {
                        LmsMode = LmsMode.LMS_SHA256_M24_H5,
                        LmOtsMode = LmOtsMode.LMOTS_SHA256_N24_W1
                    }
                ];
            }
            else
            {
                _generalCapabilities = new GeneralCapabilities
                {
                    LmsModes = [LmsMode.LMS_SHA256_M24_H5],
                    LmOtsModes = [LmOtsMode.LMOTS_SHA256_N24_W1]
                };
            }
        }

        public ParameterBuilder WithAlgoModeRevision(string algorithm, string mode, string revision)
        {
            _algorithm = algorithm;
            _mode = mode;
            _revision = revision;
            return this;
        }

        public ParameterBuilder WithMessageLength(MathDomain value)
        {
            _messageLength = value;
            return this;
        }

        public ParameterBuilder WithGeneralCapabilities(GeneralCapabilities value)
        {
            _generalCapabilities = value;
            return this;
        }

        public ParameterBuilder WithSpecificCapabilities(SpecificCapability[] value)
        {
            _specificCapabilities = value;
            return this;
        }

        public Parameters Build()
        {
            return new Parameters
            {
                Algorithm = _algorithm,
                Mode = _mode,
                Revision = _revision,
                MessageLength = _messageLength,
                Capabilities = _generalCapabilities,
                SpecificCapabilities = _specificCapabilities
            };
        }
    }
}
