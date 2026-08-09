using System.Collections.Generic;
using Newtonsoft.Json;
using NIST.CVP.ACVTS.Libraries.Crypto.Common.DRBG;
using NIST.CVP.ACVTS.Libraries.Crypto.Common.DRBG.Enums;
using NIST.CVP.ACVTS.Libraries.Generation.Core;

namespace NIST.CVP.ACVTS.Libraries.Generation.DRBG.SP800_90Ar1
{
    public class TestGroup : ITestGroup<TestGroup, TestCase>
    {
        /// <summary>
        /// Setting this property also updates the "base" equivalent properties of the class.
        /// </summary>
        [JsonIgnore]
        public DrbgParameters DrbgParameters
        {
            get => _drbgParameters;
            set
            {
                _drbgParameters = value;

                Mode = _drbgParameters.Mode;

                DerFunc = _drbgParameters.DerFuncEnabled;
                PredResistance = _drbgParameters.PredResistanceEnabled;
                ReSeed = _drbgParameters.ReseedImplemented;

                EntropyInputLen = _drbgParameters.EntropyInputLen;
                NonceLen = _drbgParameters.NonceLen;
                PersoStringLen = _drbgParameters.PersoStringLen;
                AdditionalInputLen = _drbgParameters.AdditionalInputLen;

                ReturnedBitsLen = _drbgParameters.ReturnedBitsLen;
                CounterFieldLength = _drbgParameters.CounterFieldLength;
            }
        }

        public int TestGroupId { get; set; }
        public string TestType { get; set; }

        [JsonProperty(PropertyName = "derFunc")]
        public bool DerFunc { get; set; }

        [JsonProperty(PropertyName = "reSeed")]
        public bool ReSeed { get; set; }

        [JsonProperty(PropertyName = "predResistance")]
        public bool PredResistance { get; set; }

        [JsonProperty(PropertyName = "entropyInputLen")]
        public int EntropyInputLen { get; set; }

        [JsonProperty(PropertyName = "nonceLen")]
        public int NonceLen { get; set; }

        [JsonProperty(PropertyName = "persoStringLen")]
        public int PersoStringLen { get; set; }

        [JsonProperty(PropertyName = "additionalInputLen")]
        public int AdditionalInputLen { get; set; }

        [JsonProperty(PropertyName = "returnedBitsLen")]
        public int ReturnedBitsLen { get; set; }

        [JsonProperty(PropertyName = "mode")]
        public DrbgMode Mode { get; set; }
        
        [JsonProperty(PropertyName = "counterFieldLen")]
        public int? CounterFieldLength { get; set; }
        public List<TestCase> Tests { get; set; } = new List<TestCase>();

        private DrbgParameters _drbgParameters = new DrbgParameters();
    }
}
