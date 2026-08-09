using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using NIST.CVP.ACVTS.Libraries.Common.ExtensionMethods;
using NIST.CVP.ACVTS.Libraries.Crypto.Common.DRBG;
using NIST.CVP.ACVTS.Libraries.Crypto.Common.DRBG.Enums;
using NIST.CVP.ACVTS.Libraries.Crypto.Common.DRBG.Helpers;
using NIST.CVP.ACVTS.Libraries.Generation.Core;
using NIST.CVP.ACVTS.Libraries.Math;
using NIST.CVP.ACVTS.Libraries.Math.Domain;

namespace NIST.CVP.ACVTS.Libraries.Generation.DRBG.SP800_90Ar1
{
    public class TestGroupGenerator : ITestGroupGeneratorAsync<Parameters, TestGroup, TestCase>
    {
        public const int _MAX_BIT_SIZE = 65536;

        public Task<List<TestGroup>> BuildTestGroupsAsync(Parameters parameters)
        {
            var groups = new List<TestGroup>();

            CreateGroups(groups, parameters);

            return Task.FromResult(groups);
        }

        private void CreateGroups(List<TestGroup> groups, Parameters parameters)
        {
            foreach (var predResistance in parameters.PredResistanceEnabled)
            {
                foreach (var capability in parameters.Capabilities)
                {
                    var attributes = DrbgAttributesHelper.GetDrbgAttributes(parameters.Algorithm, capability.Mode, capability.DerFuncEnabled);

                    // We don't want to generate test groups that have 1 << 35 sized lengths (as that is the cap in some cases)
                    // Set to a maximum value to generate.
                    capability.EntropyInputLen.SetMaximumAllowedValue(_MAX_BIT_SIZE);
                    capability.NonceLen.SetMaximumAllowedValue(_MAX_BIT_SIZE);
                    capability.PersoStringLen.SetMaximumAllowedValue(_MAX_BIT_SIZE);
                    capability.AdditionalInputLen.SetMaximumAllowedValue(_MAX_BIT_SIZE);
                    capability.ReturnedBitsLen.SetMaximumAllowedValue(_MAX_BIT_SIZE);

                    var testEntropyInputLens = GetTestableValuesFromCapability(capability.EntropyInputLen.GetDeepCopy());
                    var testNonceLens = GetTestableValuesFromCapability(capability.NonceLen.GetDeepCopy());
                    var testPersoStringLens = GetTestableValuesFromCapability(capability.PersoStringLen.GetDeepCopy());
                    var testAdditionalInputLens = GetTestableValuesFromCapability(capability.AdditionalInputLen.GetDeepCopy());
                    var testReturnedBitLens = GetTestableValuesFromCapability(capability.ReturnedBitsLen.GetDeepCopy());

                    var maxCount = new[]
                    {
                        testEntropyInputLens.OriginalListCount,
                        testAdditionalInputLens.OriginalListCount,
                        testNonceLens.OriginalListCount,
                        testPersoStringLens.OriginalListCount,
                        testReturnedBitLens.OriginalListCount,
                    }.Max();

                    for (var i = 0; i < maxCount; i++)
                    {
                        var entropyLen = testEntropyInputLens.Pop();
                        var nonceLen = testNonceLens.Pop();
                        var persoStringLen = testPersoStringLens.Pop();
                        var additionalInputLen = testAdditionalInputLens.Pop();
                        var returnedBitLen = testReturnedBitLens.Pop();
                        
                        var dp = new DrbgParameters
                        {
                            Mechanism = attributes.Mechanism,
                            Mode = attributes.Mode,
                            SecurityStrength = attributes.MaxSecurityStrength,

                            DerFuncEnabled = capability.DerFuncEnabled,
                            PredResistanceEnabled = predResistance,
                            ReseedImplemented = parameters.ReseedImplemented,

                            EntropyInputLen = entropyLen,
                            NonceLen = nonceLen,
                            PersoStringLen = persoStringLen,
                            AdditionalInputLen = additionalInputLen,

                            ReturnedBitsLen = returnedBitLen,
                        };
                        
                        // While the DrbgParameters class is used for ctrDRBG, hashDRBG, and hmacDRBG, DrbgParameters.CounterFieldLen
                        // is only applicable for ctrDRBG. If a ctrDRBG is being tested, the CounterFieldLen is required
                        // to be supplied in the registration, but confirm it's not null. 
                        if (attributes.Mechanism == DrbgMechanism.Counter && capability.CounterFieldLen != null)
                            dp.CounterFieldLength = (int) capability.CounterFieldLen;
                        
                        var tg = new TestGroup
                        {
                            DrbgParameters = dp,
                            TestType = "AFT",
                            CounterFieldLength = capability.CounterFieldLen
                        };

                        groups.Add(tg);
                    }
                }
            }
        }

        private ShuffleQueue<int> GetTestableValuesFromCapability(MathDomain capability)
        {
            var minMaxDomain = capability.GetDomainMinMaxAsEnumerable();
            var randomCandidates = capability.GetRandomValues(10).ToList();
            var testValues = new List<int>();
            testValues.AddRangeIfNotNullOrEmpty(minMaxDomain);
            testValues
                .AddRangeIfNotNullOrEmpty(
                    randomCandidates
                        .Except(testValues)
                        .OrderBy(ob => Guid.NewGuid())
                        .Take(2)
                );

            return new ShuffleQueue<int>(testValues);
        }
    }
}
