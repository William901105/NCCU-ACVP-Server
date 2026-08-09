using NIST.CVP.ACVTS.Libraries.Crypto.Common.DRBG.Enums;
using NIST.CVP.ACVTS.Libraries.Generation.DRBG.SP800_90Ar1;
using NIST.CVP.ACVTS.Libraries.Math.Domain;

namespace NIST.CVP.ACVTS.Libraries.Generation.Tests.DRBG.SP800_90Ar1
{
    public class ParameterBuilder
    {
        private string _algorithm;
        private string _mode;
        private bool _derFunctionEnabled;
        private bool _predResistEnabled;
        private bool _reseedImplemented;
        private MathDomain _entropyInputLen;
        private MathDomain _nonceLen;
        private MathDomain _persoStringLen;
        private MathDomain _additionalInputLen;
        private int? _counterFieldLen; 
        
        private DrbgMechanism _drbgMechanism;
        private DrbgMode _drbgMode;
        public int SeedLength { get; private set; }
        public MathDomain OutLength { get; private set; } = new MathDomain().AddSegment(new ValueDomainSegment(512));
        public int KeyLength { get; private set; } = 0;
        public int SecurityStrength { get; private set; } = 0;

        /// <summary>
        /// Provides a valid (as of construction) set of parameters
        /// </summary>
        /// <param name="mechanism"></param>
        /// <param name="mode"></param>
        /// <param name="derFunctionEnabled"></param>
        public ParameterBuilder(DrbgMechanism mechanism, DrbgMode mode, bool derFunctionEnabled = false)
        {
            _derFunctionEnabled = derFunctionEnabled;
            SetMechanism(mechanism);
            SetMode(mode);
            SetMathRanges(mechanism, mode);
            
            // the counterFieldLen property is only applicable to ctrDRBGs
            if (mechanism == DrbgMechanism.Counter)
            {
                SetCounterFieldLen(mode);
            }
        }

        public ParameterBuilder WithAlgorithm(DrbgMechanism value)
        {
            SetMechanism(value);
            return this;
        }

        public ParameterBuilder WithMode(DrbgMode value)
        {
            SetMode(value);
            return this;
        }

        public ParameterBuilder WithDerFunctionEnabled(bool value)
        {
            _derFunctionEnabled = value;
            return this;
        }

        public ParameterBuilder WithPredResistEnabled(bool value)
        {
            _predResistEnabled = value;
            return this;
        }

        public ParameterBuilder WithReseedImplemented(bool value)
        {
            _reseedImplemented = value;
            return this;
        }

        public ParameterBuilder WithEntropyInputLen(MathDomain value)
        {
            _entropyInputLen = value;
            return this;
        }

        public ParameterBuilder WithNonceLen(MathDomain value)
        {
            _nonceLen = value;
            return this;
        }

        public ParameterBuilder WithPersoStringLen(MathDomain value)
        {
            _persoStringLen = value;
            return this;
        }
        
        public ParameterBuilder WithCounterFieldLen(int? value)
        {
            _counterFieldLen = value;
            return this;
        }

        public ParameterBuilder WithAdditionalInputLen(MathDomain value)
        {
            _additionalInputLen = value;
            return this;
        }

        public ParameterBuilder WithReturnedBitsLen(MathDomain value)
        {
            OutLength = value;
            return this;
        }

        public Parameters Build()
        {
            return new Parameters()
            {
                Algorithm = _algorithm,
                Revision = "Sp800-90Ar1",
                ReseedImplemented = _reseedImplemented,
                PredResistanceEnabled = new[] { _predResistEnabled },

                Capabilities = new[]
                {
                    new Capability
                    {
                        Mode = _mode,
                        DerFuncEnabled = _derFunctionEnabled,
                        EntropyInputLen = _entropyInputLen,
                        NonceLen = _nonceLen,
                        PersoStringLen = _persoStringLen,
                        AdditionalInputLen = _additionalInputLen,
                        ReturnedBitsLen = OutLength,
                        CounterFieldLen = _counterFieldLen
                    }
                }
            };
        }

        private void SetMode(DrbgMode mode)
        {
            _drbgMode = mode;

            switch (mode)
            {
                case DrbgMode.AES128:
                    _mode = "AES-128";
                    break;
                case DrbgMode.AES192:
                    _mode = "AES-192";
                    break;
                case DrbgMode.AES256:
                    _mode = "AES-256";
                    break;
                case DrbgMode.TDES:
                    _mode = "TDES";
                    break;
                case DrbgMode.SHA1:
                    _mode = "SHA-1";
                    break;
                case DrbgMode.SHA224:
                    _mode = "SHA2-224";
                    break;
                case DrbgMode.SHA256:
                    _mode = "SHA2-256";
                    break;
                case DrbgMode.SHA384:
                    _mode = "SHA2-384";
                    break;               
                case DrbgMode.SHA512:
                    _mode = "SHA2-512";
                    break;
                case DrbgMode.SHA512t224:
                    _mode = "SHA2-512/224";
                    break;
                case DrbgMode.SHA512t256:
                    _mode = "SHA2-512/256";
                    break;               
            }
        }

        private void SetMechanism(DrbgMechanism mechanism)
        {
            _drbgMechanism = mechanism;

            switch (mechanism)
            {
                case DrbgMechanism.Counter:
                    _algorithm = "ctrDRBG";
                    break;
                case DrbgMechanism.Hash:
                    _algorithm = "hashDRBG";
                    break;
                default:
                    _algorithm = "invalid";
                    break;
            }
        }

        private void SetMathRanges(DrbgMechanism mechanism, DrbgMode mode)
        {
            switch (mode)
            {
                case DrbgMode.AES128:
                    KeyLength = 128;
                    SecurityStrength = 128;
                    OutLength.AddSegment(new ValueDomainSegment(128));
                    break;
                case DrbgMode.AES192:
                    KeyLength = 192;
                    SecurityStrength = 192;
                    OutLength.AddSegment(new ValueDomainSegment(128));
                    break;
                case DrbgMode.AES256:
                    KeyLength = 256;
                    SecurityStrength = 256;
                    OutLength.AddSegment(new ValueDomainSegment(128));
                    break;
                case DrbgMode.TDES:
                    KeyLength = 168;
                    SecurityStrength = 112;
                    OutLength.AddSegment(new ValueDomainSegment(64));
                    break;
                case DrbgMode.SHA1:
                    SecurityStrength = 128;
                    OutLength.AddSegment(new ValueDomainSegment(160));
                    break;
                case DrbgMode.SHA224:
                    SecurityStrength = 192;
                    OutLength.AddSegment(new ValueDomainSegment(224));
                    break;
                case DrbgMode.SHA256:
                    SecurityStrength = 256;
                    OutLength.AddSegment(new ValueDomainSegment(256));
                    break;
                case DrbgMode.SHA384:
                    SecurityStrength = 256;
                    OutLength.AddSegment(new ValueDomainSegment(384));
                    break;               
                case DrbgMode.SHA512:
                    SecurityStrength = 256;
                    OutLength.AddSegment(new ValueDomainSegment(512));
                    break;
                case DrbgMode.SHA512t224:
                    SecurityStrength = 192;
                    OutLength.AddSegment(new ValueDomainSegment(224));
                    break;
                case DrbgMode.SHA512t256:
                    SecurityStrength = 256;
                    OutLength.AddSegment(new ValueDomainSegment(256));
                    break;               
            }

            if (mechanism == DrbgMechanism.Counter)
            {
                SeedLength = OutLength.GetDomainMinMax().Minimum + KeyLength;
                
                _additionalInputLen = new MathDomain();
                _additionalInputLen.AddSegment(new ValueDomainSegment(SeedLength));

                _entropyInputLen = new MathDomain();
                _entropyInputLen.AddSegment(new ValueDomainSegment(SeedLength));
                
                _persoStringLen = new MathDomain();
                _persoStringLen.AddSegment(new ValueDomainSegment(SeedLength));

                _nonceLen = new MathDomain();
                // if !derFunctionEnabled, no nonce is used. A value of zero is used to indicate this.
                var nonceLen = _derFunctionEnabled == true ? SeedLength : 0;
                _nonceLen.AddSegment(new ValueDomainSegment(nonceLen));
            } else if (mechanism == DrbgMechanism.Hash)
            {
                _additionalInputLen = new MathDomain();
                _additionalInputLen.AddSegment(new ValueDomainSegment(SecurityStrength));

                _entropyInputLen = new MathDomain();
                _entropyInputLen.AddSegment(new ValueDomainSegment(SecurityStrength));

                _nonceLen = new MathDomain();
                _nonceLen.AddSegment(new ValueDomainSegment(SecurityStrength/2));

                _persoStringLen = new MathDomain();
                _persoStringLen.AddSegment(new ValueDomainSegment(SecurityStrength));
            }
        }
        
        private void SetCounterFieldLen(DrbgMode mode)
        {
            // Default counterFieldLen to the value defined for blocklen in SP 800-90Ar1 Table 3.
            if (mode.ToString().Contains("AES"))
                _counterFieldLen = 128;
            else if (mode.ToString().Contains("TDES"))  
                _counterFieldLen = 64;
        }
    }
}
