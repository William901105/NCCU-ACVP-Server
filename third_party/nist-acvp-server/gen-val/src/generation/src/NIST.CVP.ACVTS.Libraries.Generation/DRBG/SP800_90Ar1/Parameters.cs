using NIST.CVP.ACVTS.Libraries.Generation.Core;
using NIST.CVP.ACVTS.Libraries.Math.Domain;

namespace NIST.CVP.ACVTS.Libraries.Generation.DRBG.SP800_90Ar1
{
    public class Parameters : IParameters
    {
        public int VectorSetId { get; set; }
        public string Algorithm { get; set; } // "ctrDRBG/hashDRBG/hmacDRBG"
        public string Mode { get; set; } = null;
        public string Revision { get; set; }
        public bool IsSample { get; set; }
        public string[] Conformances { get; set; } = { };
        public bool[] PredResistanceEnabled { get; set; }
        public bool ReseedImplemented { get; set; }
        public Capability[] Capabilities { get; set; }
    }

    public class Capability
    {
        public string Mode { get; set; }
        public bool DerFuncEnabled { get; set; }
        public MathDomain EntropyInputLen { get; set; }
        public MathDomain NonceLen { get; set; }
        public MathDomain PersoStringLen { get; set; }
        public MathDomain AdditionalInputLen { get; set; }
        public MathDomain ReturnedBitsLen { get; set; }
        // CounterFieldLen is nullable because the Capability class is used for ctrDRBG, hashDRBG, and hmacDRBG, but 
        // CounterFieldLen is only valid for ctrDRBG.
        public int? CounterFieldLen { get; set; }
    }
}
