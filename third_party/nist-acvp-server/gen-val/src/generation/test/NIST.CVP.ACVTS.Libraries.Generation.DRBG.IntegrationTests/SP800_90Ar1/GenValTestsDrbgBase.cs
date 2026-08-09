using NIST.CVP.ACVTS.Libraries.Common;
using NIST.CVP.ACVTS.Libraries.Generation.DRBG.SP800_90Ar1;
using NIST.CVP.ACVTS.Libraries.Generation.Tests;
using NIST.CVP.ACVTS.Libraries.Math;
using NIST.CVP.ACVTS.Libraries.Math.Domain;

namespace NIST.CVP.ACVTS.Libraries.Generation.DRBG.IntegrationTests.SP800_90Ar1
{
    public abstract class GenValTestsDrbgBase : GenValTestsSingleRunnerBase
    {
        public abstract override string Algorithm { get; }
        public override string Mode { get; } = null;

        public abstract string[] Modes { get; }
        public abstract int[] SeedLength { get; }


        public override IRegisterInjections RegistrationsGenVal => new RegisterInjections();

        protected override void ModifyTestCaseToFail(dynamic testCase)
        {
            var rand = new Random800_90();

            // If TC has a returnedBIts, change it
            if (testCase.returnedBits != null)
            {
                var bs = new BitString(testCase.returnedBits.ToString());
                bs = rand.GetDifferentBitStringOfSameSize(bs);

                testCase.returnedBits = bs.ToHex();
            }
        }

        protected override string GetTestFileFewTestCases(string targetFolder)
        {
            var index = 0;
            var otherIndex = 1;
            var tdesIndex = 3;

            var p = new Parameters
            {
                Algorithm = Algorithm,
                Revision = Revision,
                ReseedImplemented = true,
                PredResistanceEnabled = new[] { true },
                Capabilities = new[]
                {
                    new Capability
                    {
                        Mode = Modes[index],
                        NonceLen = new MathDomain().AddSegment(new ValueDomainSegment(SeedLength[index])),
                        AdditionalInputLen = new MathDomain().AddSegment(new RangeDomainSegment(new Random800_90(), SeedLength[index], SeedLength[index] + 64, 64)),
                        PersoStringLen = new MathDomain().AddSegment(new ValueDomainSegment(SeedLength[index])),
                        EntropyInputLen = new MathDomain().AddSegment(new ValueDomainSegment(SeedLength[index])),
                        ReturnedBitsLen = new MathDomain().AddSegment(new ValueDomainSegment(256)),
                        DerFuncEnabled = true,
                        CounterFieldLen = 128,
                    },
                    new Capability
                    {
                        Mode = Modes[otherIndex],
                        NonceLen = new MathDomain().AddSegment(new ValueDomainSegment(0)),
                        AdditionalInputLen = new MathDomain().AddSegment(new ValueDomainSegment(SeedLength[otherIndex])),
                        PersoStringLen = new MathDomain().AddSegment(new ValueDomainSegment(SeedLength[otherIndex])),
                        EntropyInputLen = new MathDomain().AddSegment(new ValueDomainSegment(SeedLength[otherIndex])),
                        ReturnedBitsLen = new MathDomain().AddSegment(new ValueDomainSegment(256)),
                        DerFuncEnabled = false,
                        CounterFieldLen = 4,
                    },
                    new Capability
                    {
                        Mode = Modes[tdesIndex],
                        NonceLen = new MathDomain().AddSegment(new ValueDomainSegment(0)),
                        AdditionalInputLen = new MathDomain().AddSegment(new ValueDomainSegment(SeedLength[tdesIndex])),
                        PersoStringLen = new MathDomain().AddSegment(new ValueDomainSegment(SeedLength[tdesIndex])),
                        EntropyInputLen = new MathDomain().AddSegment(new ValueDomainSegment(SeedLength[tdesIndex])),
                        ReturnedBitsLen = new MathDomain().AddSegment(new ValueDomainSegment(256)),
                        DerFuncEnabled = false,
                        CounterFieldLen = 64,
                    }
                }
            };

            return CreateRegistration(targetFolder, p);
        }

        protected override string GetTestFileLotsOfTestCases(string targetFolder)
        {
            var capabilities = new Capability[Modes.Length * 2];
            
            for (var i = 0; i < Modes.Length; i++)
            {
                capabilities[i + 0 * Modes.Length] = new Capability
                {
                    Mode = Modes[i],
                    NonceLen = new MathDomain().AddSegment(new ValueDomainSegment(SeedLength[i])),
                    AdditionalInputLen = new MathDomain().AddSegment(new ValueDomainSegment(SeedLength[i])),
                    PersoStringLen = new MathDomain().AddSegment(new ValueDomainSegment(SeedLength[i])),
                    EntropyInputLen = new MathDomain().AddSegment(new ValueDomainSegment(SeedLength[i])),
                    ReturnedBitsLen = new MathDomain().AddSegment(new ValueDomainSegment(128)).AddSegment(new ValueDomainSegment(256)),
                    DerFuncEnabled = true
                };
                capabilities[i + 1 * Modes.Length] = new Capability
                {
                    Mode = Modes[i],
                    NonceLen = new MathDomain().AddSegment(new ValueDomainSegment(0)),
                    AdditionalInputLen = new MathDomain().AddSegment(new ValueDomainSegment(SeedLength[i])),
                    PersoStringLen = new MathDomain().AddSegment(new ValueDomainSegment(SeedLength[i])),
                    EntropyInputLen = new MathDomain().AddSegment(new ValueDomainSegment(SeedLength[i])),
                    ReturnedBitsLen = new MathDomain().AddSegment(new ValueDomainSegment(128)),
                    DerFuncEnabled = false
                };

                if (Modes[i].Contains("AES")) // 3 of the 4 defined modes are AES
                {
                    capabilities[i + 0 * Modes.Length].CounterFieldLen = 128;
                    capabilities[i + 1 * Modes.Length].CounterFieldLen = 64;    
                }
                else // the 4th is TDES
                {
                    capabilities[i + 0 * Modes.Length].CounterFieldLen = 64;
                    capabilities[i + 1 * Modes.Length].CounterFieldLen = 4;   
                }
            }

            Parameters p = new Parameters
            {
                Algorithm = Algorithm,
                Revision = Revision,
                ReseedImplemented = true,
                PredResistanceEnabled = new[] { true, false },
                Capabilities = capabilities
            };

            return CreateRegistration(targetFolder, p);
        }
    }
}
